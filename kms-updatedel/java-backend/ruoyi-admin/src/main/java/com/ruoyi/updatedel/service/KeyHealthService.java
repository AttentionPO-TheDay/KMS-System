package com.ruoyi.updatedel.service;

import com.ruoyi.common.crypto.KeyMaterialEpoch;
import com.ruoyi.updatedel.domain.KeyHealthResult;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.mapper.KeyOperationRecordMapper;
import java.util.List;
import java.util.Comparator;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * 密钥健康检查（阶段 7，文档 §8.1 一致性检查 + §8.2 异常检测）。
 *
 * <h2>为什么合并成一个服务</h2>
 * 一致性检查要的是「这段记录与那份记录对得上吗」，异常检测要的是
 * 「这条记录像不像出问题了」——两者读的是**同一份数据**（密钥本体 +
 * 操作轨迹 + 版本历史）。拆成两个服务只会把同样的表扫两遍，
 * 而且会出现"一致性说 OK、异常检测说可疑"这种自相矛盾的输出。
 *
 * <h2>为什么全是规则、没有模型</h2>
 * 文档 §8.2 明确「第一版采用规则，不引入复杂 AI」。规则的好处是
 * **每条告警都能被人读懂并反驳**：命中哪条规则、依据是什么、该怎么处理，
 * 三样都写清楚。一个说不出理由的"异常分数"在运维现场没有用。
 *
 * <h2>规则的判定口径</h2>
 * 所有规则都基于**可观测的记录**，不做推测。例如"版本不一致"要求
 * 同时存在两条可比较的记录（当前版本 vs 最近操作记录的版本），
 * 缺任一条就只记为观测值、不给结论 —— 宁可漏报，不要编造。
 */
@Service
public class KeyHealthService {

    @Autowired
    private KeymanageMapper keymanageMapper;

    @Autowired
    private KeyOperationRecordMapper keyOperationRecordMapper;

    /**
     * 对一把密钥做完整健康检查。
     *
     * @param keyId 密钥 ID
     * @return 检查结果；密钥不存在时返回 null，由调用方给出 404
     */
    public KeyHealthResult check(Long keyId) {
        Keymanage key = keymanageMapper.selectkeymanageByKeyId(keyId);
        if (key == null) {
            return null;
        }

        KeyHealthResult r = new KeyHealthResult();
        r.setKeyId(key.getKeyId());
        r.setKeyName(key.getKeyName());
        r.setVersion(key.getVersion());
        r.setStatus(key.getStatus());

        checkRevoked(r, key);
        checkMaterialState(r, key);
        checkMaterialPresence(r, key);
        checkOperationTrail(r, key);

        // 回收是终态：上面若有规则把它拉成 REVOKED，这里不再回退成 OK。
        // 顺序反过来（先判回收）会被后续的 observe 覆盖掉结论。
        if (KeyHealthResult.REVOKED.equals(r.getHealth()) && !isRevoked(key)) {
            // 被规则判成 REVOKED 但不是回收状态 —— 保留结论，因为
            // "材料不可用"比"状态字段怎么写"更能反映实际能不能用。
            r.observe("注意：密钥状态字段为 " + key.getStatus() + "，但检查判定其材料不可用");
        }
        return r;
    }

    private boolean isRevoked(Keymanage key) {
        return "3".equals(key.getStatus());
    }

    // ------------------------------------------------------------------
    // §8.2 异常检测：状态与材料
    // ------------------------------------------------------------------

    /** 已回收的密钥：不是"异常"，是正常终态，但也不该再被使用。 */
    private void checkRevoked(KeyHealthResult r, Keymanage key) {
        if (isRevoked(key)) {
            r.setHealth(KeyHealthResult.REVOKED);
            r.observe("密钥已回收（status=3）：不应再用于分发、签名或更新");
        } else {
            r.observe("密钥状态：" + key.getStatus() + "（0=有效 1=冻结 2=轮换 3=回收）");
        }
    }

    /**
     * §8.1：材料可用性与版本标记是否自洽。
     *
     * <p>历史上出现过一批 `legacy_unusable` 记录 —— 它们不是故障，
     * 而是"用户侧本地份额从未持久化"这一设计的结果（见 KeyMaterialEpoch 说明）。
     * 单独标出来是为了让运维一眼区分"设计如此"与"出问题了"。
     */
    private void checkMaterialState(KeyHealthResult r, Keymanage key) {
        String state = key.getKeyMaterialState();
        if (state == null || state.trim().isEmpty()) {
            r.observe("材料状态未标记（早期记录无此字段，按历史数据处理）");
            return;
        }
        if (KeyMaterialEpoch.STATE_LEGACY_UNUSABLE.equals(state)) {
            r.observe("材料状态：legacy_unusable —— 属早期密钥的已知情况（用户侧份额未持久化），"
                + "不是故障；这些记录无法再解开任何东西");
            return;
        }
        r.observe("材料状态：" + state);
    }

    /**
     * §8.2：公钥份额缺失。
     *
     * <p>{@code ua} 是用户部分公钥、{@code key_value} 是 KGC 部分密钥 ——
     * 无证书方案里这两者缺一不可：少了 ua 就无法复算最终公钥 P_A，
     * 少了 key_value 就无法参与组合出 d_A。任一为空都说明记录不完整。
     */
    private void checkMaterialPresence(KeyHealthResult r, Keymanage key) {
        boolean hasUa = notBlank(key.getUa());
        boolean hasValue = notBlank(key.getKeyValue());

        if (!hasUa && !hasValue) {
            r.error("material-missing",
                "公钥份额 ua 与 KGC 部分密钥 keyValue 同时为空",
                "该记录无法用于任何密码学操作。若确认已废弃，请回收；否则需重新签发");
        } else if (!hasUa) {
            r.warn("ua-missing",
                "公钥份额 ua 为空",
                "无法复算最终公钥 P_A，历史分发的信封可能无法核对。建议核实该密钥的签发记录");
        } else if (!hasValue) {
            r.warn("keyvalue-missing",
                "KGC 部分密钥 keyValue 为空",
                "无法组合出完整私钥。若用户侧仍持有份额，可走一次密钥更新重新签发部分密钥");
        } else {
            r.observe("材料齐备：ua " + key.getUa().length() + " 字符，keyValue " + key.getKeyValue().length() + " 字符");
        }
    }

    /**
     * §8.1：当前版本与最近一次操作记录的版本是否一致。
     *
     * <p>口径说明：轮换会同时写 keymanage.version+1 与一条 UPDATE 操作记录。
     * 两者本该同步推进，不一致说明有一步没落库 —— 这是**明确的一致性缺陷**，
     * 不是猜测。
     *
     * <p>只在"两条记录都存在且都可比较"时才判定：缺任一条只记观测值。
     * 宁可漏报，也不要把"没有记录"说成"记录不一致"。
     */
    private void checkOperationTrail(KeyHealthResult r, Keymanage key) {
        List<KeyOperationRecord> records;
        try {
            KeyOperationRecord query = new KeyOperationRecord();
            query.setKeyId(key.getKeyId());
            records = keyOperationRecordMapper.selectKeyOperationRecordList(query);
        } catch (RuntimeException ex) {
            // 操作记录查不到不该让整个健康检查失败 —— 其余规则仍然有价值
            r.observe("操作轨迹不可读：" + ex.getMessage());
            return;
        }

        if (records == null || records.isEmpty()) {
            r.observe("无操作记录（可能是阶段 4 之前的存量密钥）");
            return;
        }

        r.observe("操作记录 " + records.size() + " 条");

        // Mapper 已按 action_time DESC、record_id DESC 返回；健康检查的“最近操作”
        // 必须按时间选择，不能按最大版本号选择。补录、重试或历史数据修复时，
        // 版本号可能高于当前最新操作，按版本取最大值会把旧记录误判成最新记录。
        KeyOperationRecord latest = records.stream()
            .filter(rec -> rec.getActionTime() != null)
            .max(Comparator.comparing(KeyOperationRecord::getActionTime)
                .thenComparing(rec -> rec.getRecordId() == null ? Long.MIN_VALUE : rec.getRecordId()))
            .orElse(records.get(0));

        Integer current = key.getVersion();
        Integer recorded = latest.getKeyVersion();
        if (current != null && recorded != null && !current.equals(recorded)) {
            r.warn("version-drift",
                "当前版本 v" + current + " 与最近操作记录中的版本 v" + recorded + " 不一致",
                "可能是轮换只写了一张表。请核对密钥更新记录，必要时以链上存证为准复核");
        } else if (current != null && recorded != null) {
            r.observe("版本一致：v" + current);
        }

        // 上链失败是常见且可修复的问题，单独提示
        for (KeyOperationRecord rec : records) {
            if ("2".equals(rec.getChainStatus())) {
                r.warn("chain-failed",
                    "存在上链失败的操作记录（recordId=" + rec.getRecordId() + "）",
                    "该次操作的链上存证缺失。可靠性要求高时可重新触发上链，或如实记录为未存证");
                break;
            }
        }
    }

    private boolean notBlank(String s) {
        return s != null && !s.trim().isEmpty();
    }
}
