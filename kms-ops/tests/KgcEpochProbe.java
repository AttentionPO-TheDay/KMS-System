import com.ruoyi.common.crypto.KgcMasterSecret;

/**
 * 验证 KGC 主私钥的版本化行为（不启动 Spring，直接调静态入口）。
 *
 * 关键主张：**轮换 ms 之后，历史记录仍能按自己那一版复算 P_A。**
 * 这条成立的前提是：
 *   1. 旧 ms 仍在密钥集里（作为退役版本，而不是被删掉）；
 *   2. 按版本取密钥这件事本身是对的 —— 取不到的版本要**明确报错**，
 *      绝不能静默回退到启用版本（那会让历史记录算出错误的 P_A，且毫无提示）。
 */
public class KgcEpochProbe {

    private static int pass = 0;
    private static int fail = 0;

    private static void check(String name, boolean ok, String detail) {
        if (ok) {
            pass++;
            System.out.println("  [OK]   " + name + (detail.isEmpty() ? "" : "  " + detail));
        } else {
            fail++;
            System.out.println("  [FAIL] " + name + (detail.isEmpty() ? "" : "  " + detail));
        }
    }

    private static String shortOf(String hex) {
        return hex == null ? "null" : hex.substring(0, 10) + "…(len " + hex.length() + ")";
    }

    public static void main(String[] args) {
        System.out.println("=== KGC 主私钥版本化验证 ===\n");

        String activeId = KgcMasterSecret.activeId();
        check("启用版本可读出", activeId != null && !activeId.isEmpty(), "activeId=" + activeId);

        String active = KgcMasterSecret.getActive();
        check("启用密钥可用", active != null && active.length() == 64, shortOf(active));

        // ---- 核心：旧 ms 必须仍在密钥集里 ----
        String v1 = KgcMasterSecret.getById("ms_v1");
        check("★ 退役版本 ms_v1 仍可取到（历史 P_A 才可能复算）",
            v1 != null && v1.length() == 64, shortOf(v1));
        check("★ ms_v1 就是历史上那个公开演示值（即历史记录真正的签名密钥）",
            KgcMasterSecret.LEGACY_DEMO_SECRET.equalsIgnoreCase(v1), "");
        check("ms_v1 已退役（不再用于签发）", KgcMasterSecret.isRetired("ms_v1"), "");

        String v2 = KgcMasterSecret.getById("ms_v2");
        check("启用版本 ms_v2 可取到", v2 != null && v2.length() == 64, shortOf(v2));
        check("两个版本的密钥**不相同**（确实轮换过）",
            !v1.equalsIgnoreCase(v2), "v1=" + shortOf(v1) + " v2=" + shortOf(v2));
        check("ms_v2 未退役", !KgcMasterSecret.isRetired("ms_v2"), "");

        // ---- 早期记录没有 ms_key_id 字段，必须按 ms_v1 处理 ----
        check("★ ms_key_id 为空 → 按 ms_v1 处理（早期记录没有该字段）",
            KgcMasterSecret.LEGACY_DEMO_SECRET.equalsIgnoreCase(KgcMasterSecret.getById(null)), "");
        check("ms_key_id 为空白串 → 同样按 ms_v1 处理",
            KgcMasterSecret.LEGACY_DEMO_SECRET.equalsIgnoreCase(KgcMasterSecret.getById("   ")), "");

        // ---- 取不到的版本必须明确失败，不能静默回退 ----
        boolean threw = false;
        String message = "";
        try {
            KgcMasterSecret.getById("ms_v999");
        } catch (IllegalStateException ex) {
            threw = true;
            message = ex.getMessage();
        }
        check("★ 未知版本明确抛错（不静默回退到启用版本）", threw,
            message.isEmpty() ? "（没有抛异常！）" : message.substring(0, Math.min(50, message.length())) + "…");
        check("报错信息提示了补救办法（补进 RETIRED，而不是删掉）",
            message.contains("RETIRED"), "");

        // ---- 演示值不得作为启用密钥 ----
        check("演示值没有被当作启用密钥（否则服务起不来）",
            !KgcMasterSecret.LEGACY_DEMO_SECRET.equalsIgnoreCase(active), "");
        check("isUsingDemoDefault() 为 false", !KgcMasterSecret.isUsingDemoDefault(), "");

        System.out.println("\n=== 结果：" + pass + " 通过 / " + fail + " 失败 ===");
        if (fail > 0) {
            System.exit(1);
        }
        System.out.println("历史版本仍可复算，且未知版本会明确失败而非静默算错。");
    }
}