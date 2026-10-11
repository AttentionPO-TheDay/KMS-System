package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.KeyHealthResult;
import com.ruoyi.updatedel.domain.KeyHealthScanItem;
import com.ruoyi.updatedel.domain.KeyHealthScanRun;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeyHealthScanMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * KMS-022：批量一致性检查（用户密钥侧）。
 *
 * <h2>为什么复用 KeyHealthService 而不是重写规则</h2>
 * 阶段 7 的 {@link KeyHealthService} 已经定了四条规则（回收态 / 材料状态标记 /
 * 材料齐备 / 操作轨迹）并写清了每条的口径。批量扫描若另写一套，两份规则必然
 * 漂移，而漂移的表现是"单钥页说 OK、批量页说 WARN"—— 用户无法判断该信哪个。
 * 所以这里逐钥调用同一个 {@code check(keyId)}，只负责**聚合与落库**。
 *
 * <h2>为什么逐钥判定而不是一条 SQL 扫全表</h2>
 * 规则要读 ua / key_value 的存在与长度、要读该钥的操作轨迹（每把钥一条查询），
 * 这不是一条 SQL 能表达的。代价是 O(n) 次查询，因此本实现用 keyset 分页
 * 分批推进，并对单次扫描的条数设上限（默认 2000，可配置）—— 触顶时
 * 在 run 行里写入**真实的剩余条数**，页面照实显示，绝不让 total 冒充全量。
 *
 * <h2>事务口径</h2>
 * 与 AutoUpdateRunService 相同：本类**不加** {@code @Transactional}。
 * 扫描不改任何密钥，没有"整批回滚"的语义需求；反过来，外层事务会把
 * 逐钥查询全部拖进一个长事务，把 run 行也锁在里面。run 行先落、明细批量写、
 * 最后回填计数，中途崩溃留下 finished_at 为 NULL 的行——那是如实记录。
 */
@Service
public class KeyHealthScanService {
    private static final Logger log = LoggerFactory.getLogger(KeyHealthScanService.class);

    /** 候选分批读取的批大小（每批一次 SQL，然后逐钥判定）。 */
    private static final int TARGET_BATCH_SIZE = 500;
    private static final int ITEM_CHUNK_SIZE = 500;
    private static final int RULE_MAX_LENGTH = 255;
    private static final int SUMMARY_MAX_LENGTH = 500;

    public static final String VERDICT_OK = "OK";
    public static final String VERDICT_WARN = "WARN";
    public static final String VERDICT_ERROR = "ERROR";
    public static final String SCOPE_ALL = "ALL";
    public static final String SCOPE_OWNER = "OWNER";

    private final KeyHealthScanMapper keyHealthScanMapper;
    private final KeymanageMapper keymanageMapper;
    private final KeyHealthService keyHealthService;

    /**
     * 单次扫描的密钥条数上限。存在的理由：扫描是同步 HTTP 请求，
     * 逐钥两次查询的代价是 O(n)；不设上限时一个大表会把请求拖到超时，
     * 而超时的表现是"点了按钮什么都没有"，且 run 行停在未完成。
     */
    @Value("${kms.lifecycle.health-scan.max-keys:2000}")
    private int maxKeysPerScan;

    public KeyHealthScanService(KeyHealthScanMapper keyHealthScanMapper,
                                KeymanageMapper keymanageMapper,
                                KeyHealthService keyHealthService) {
        this.keyHealthScanMapper = keyHealthScanMapper;
        this.keymanageMapper = keymanageMapper;
        this.keyHealthService = keyHealthService;
    }

    /**
     * 跑一轮扫描。
     *
     * @param scopeUserId 非空 = 只扫该用户的密钥（普通用户由 Controller 强制
     *                    收敛为自己的 id）；空 = 全量（仅管理员）
     * @return 收尾后的 run 行（含四项计数与如实备注）
     */
    public KeyHealthScanRun scan(Long scopeUserId) {
        Date startedAt = new Date();
        KeyHealthScanRun run = new KeyHealthScanRun();
        run.setRunId(UUID.randomUUID().toString());
        run.setUserId(scopeUserId);
        run.setScope(scopeUserId == null ? SCOPE_ALL : SCOPE_OWNER);
        run.setStartedAt(startedAt);
        keyHealthScanMapper.insertRun(run);

        int limit = maxKeysPerScan <= 0 ? 2000 : maxKeysPerScan;
        List<KeyHealthScanItem> items = new ArrayList<>();
        int scanned = 0;
        int okCount = 0;
        int warnCount = 0;
        int errorCount = 0;
        int vanished = 0;
        boolean truncated = false;
        long afterKeyId = 0L;

        while (true) {
            List<Keymanage> batch = keymanageMapper.selectScanTargets(scopeUserId, afterKeyId, TARGET_BATCH_SIZE);
            if (batch == null || batch.isEmpty()) {
                break;
            }
            for (Keymanage target : batch) {
                if (scanned >= limit) {
                    truncated = true;
                    break;
                }
                afterKeyId = target.getKeyId() == null ? afterKeyId : target.getKeyId();
                KeyHealthResult result = keyHealthService.check(target.getKeyId());
                if (result == null) {
                    // 扫描途中被删除：跳过且**不计入任何桶**。把它算成 OK 是编造，
                    // 算成 ERROR 是误报 —— 它已经不在了。
                    vanished++;
                    continue;
                }
                KeyHealthScanItem item = buildItem(run.getRunId(), target, result);
                if (VERDICT_ERROR.equals(item.getVerdict())) {
                    errorCount++;
                } else if (VERDICT_WARN.equals(item.getVerdict())) {
                    warnCount++;
                } else {
                    okCount++;
                }
                scanned++;
                items.add(item);
            }
            if (truncated || batch.size() < TARGET_BATCH_SIZE) {
                break;
            }
        }

        String note = buildNote(truncated, scopeUserId, afterKeyId, vanished, limit);
        // 所有明细持久化成功后再收尾；写失败向上传播，批次保持未完成。
        insertItems(items);
        Date finishedAt = new Date();
        keyHealthScanMapper.finishRun(run.getRunId(), finishedAt, scanned, okCount, warnCount, errorCount, note);

        log.info("key health scan finished: runId={}, scope={}, total={}, ok={}, warn={}, error={}, truncated={}",
            run.getRunId(), run.getScope(), scanned, okCount, warnCount, errorCount, truncated);

        run.setFinishedAt(finishedAt);
        run.setTotal(scanned);
        run.setOkCount(okCount);
        run.setWarnCount(warnCount);
        run.setErrorCount(errorCount);
        run.setNote(note);
        return run;
    }

    public List<KeyHealthScanRun> listRuns(KeyHealthScanRun query) {
        return keyHealthScanMapper.selectRunList(query);
    }

    public List<KeyHealthScanItem> listItems(KeyHealthScanItem query) {
        return keyHealthScanMapper.selectItemList(query);
    }

    /**
     * 把一次判定压成一行明细。verdict 的口径见 {@link KeyHealthScanItem} 类注释：
     * 只看 findings 的严重级，不看 health（REVOKED 既是"材料缺失"也是"已回收"，
     * 后者是正常终态，一律算异常会让异常桶被已回收密钥淹没）。
     */
    private KeyHealthScanItem buildItem(String runId, Keymanage target, KeyHealthResult result) {
        KeyHealthScanItem item = new KeyHealthScanItem();
        item.setRunId(runId);
        item.setKeyId(target.getKeyId());
        item.setUserId(target.getUserId());
        item.setUserName(target.getUserName());
        item.setKeyName(target.getKeyName());
        item.setEncrytName(target.getEncrytName());
        item.setKeyVersion(result.getVersion() == null ? target.getVersion() : result.getVersion());

        String verdict = VERDICT_OK;
        Set<String> rules = new LinkedHashSet<>();
        List<String> messages = new ArrayList<>();
        if (result.getFindings() != null) {
            for (KeyHealthResult.Finding finding : result.getFindings()) {
                if ("ERROR".equals(finding.getSeverity())) {
                    verdict = VERDICT_ERROR;
                } else if ("WARN".equals(finding.getSeverity()) && !VERDICT_ERROR.equals(verdict)) {
                    verdict = VERDICT_WARN;
                }
                if (finding.getRule() != null && !finding.getRule().trim().isEmpty()) {
                    rules.add(finding.getRule().trim());
                }
                if (finding.getMessage() != null && !finding.getMessage().trim().isEmpty()) {
                    messages.add(finding.getMessage().trim());
                }
            }
        }
        item.setVerdict(verdict);
        item.setRule(abbreviate(String.join(",", rules), RULE_MAX_LENGTH));
        if (messages.isEmpty()) {
            // 无 finding 时也要说清"为什么判 OK"——已回收是终态，不是异常，
            // 但页面上必须写出来，否则用户会问"这把明明是回收的，怎么是 OK"。
            boolean revoked = KeyHealthResult.REVOKED.equals(result.getHealth());
            item.setSummary(!VERDICT_OK.equals(verdict)
                ? "命中一致性问题规则，但未提供问题说明"
                : revoked ? "已回收（终态）；未发现一致性问题或异常" : "未发现一致性问题或异常");
        } else {
            item.setSummary(abbreviate(String.join("；", messages), SUMMARY_MAX_LENGTH));
        }
        return item;
    }

    /**
     * 备注只写**真实发生过**的事：触顶时是"还剩多少把"（现查），
     * 扫描期间消失的密钥数也如实记 —— 不写"可能还有"，也不把消失说成通过。
     */
    private String buildNote(boolean truncated, Long scopeUserId, long afterKeyId, int vanished, int limit) {
        List<String> parts = new ArrayList<>();
        if (truncated) {
            int remaining = keymanageMapper.countScanTargetsAfter(scopeUserId, afterKeyId);
            parts.add("达到单次扫描上限 " + limit + " 条，剩余 " + remaining
                + " 把未扫描（可调大 kms.lifecycle.health-scan.max-keys 或按用户分批扫描）");
        }
        if (vanished > 0) {
            parts.add("扫描期间有 " + vanished + " 把密钥被删除，已跳过（未计入任何结论）");
        }
        if (parts.isEmpty()) {
            return null;
        }
        return abbreviate(String.join("；", parts), 255);
    }

    private String abbreviate(String text, int max) {
        return text.length() <= max ? text : text.substring(0, max - 8) + "...(截断)";
    }

    private void insertItems(List<KeyHealthScanItem> items) {
        for (int i = 0; i < items.size(); i += ITEM_CHUNK_SIZE) {
            List<KeyHealthScanItem> chunk = items.subList(i, Math.min(i + ITEM_CHUNK_SIZE, items.size()));
            if (keyHealthScanMapper.insertItems(chunk) != chunk.size()) {
                throw new IllegalStateException("健康扫描明细未完整落库，runId=" + items.get(0).getRunId());
            }
        }
    }
}