package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.mapper.KeyOperationRecordMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class KeyOperationRecordService {
    private static final Logger log = LoggerFactory.getLogger(KeyOperationRecordService.class);
    private static final int BATCH_PROOF_REFRESH_RETRIES = 5;
    private static final long BATCH_PROOF_REFRESH_BACKOFF_MS = 120L;

    private final KeyOperationRecordMapper keyOperationRecordMapper;
    private final KeymanageMapper keymanageMapper;

    public KeyOperationRecordService(KeyOperationRecordMapper keyOperationRecordMapper, KeymanageMapper keymanageMapper) {
        this.keyOperationRecordMapper = keyOperationRecordMapper;
        this.keymanageMapper = keymanageMapper;
    }

    @Transactional
    public void createPendingRecord(Keymanage keymanage, String actionType, String actionSource, String resultMessage) {
        KeyOperationRecord record = new KeyOperationRecord();
        record.setKeyId(keymanage.getKeyId());
        record.setUserId(keymanage.getUserId());
        record.setUserName(keymanage.getUserName());
        record.setKeyName(keymanage.getKeyName());
        record.setEncrytType(keymanage.getEncrytType());
        record.setEncrytName(keymanage.getEncrytName());
        record.setKeyVersion(keymanage.getVersion());
        record.setActionType(actionType);
        record.setActionSource(actionSource);
        record.setResultStatus("0");
        record.setChainStatus(keymanage.getChainStatus());
        applyProofFields(record, keymanage);
        record.setResultMessage(resultMessage);
        record.setReceiveStatus("0");
        record.setActionTime(new Date());
        keyOperationRecordMapper.insertKeyOperationRecord(record);
    }

    @Transactional
    public void createPendingRecords(List<Keymanage> keymanages, String actionType, String actionSource, String resultMessage) {
        if (keymanages == null || keymanages.isEmpty()) {
            return;
        }
        List<KeyOperationRecord> records = new ArrayList<>(keymanages.size());
        Date actionTime = new Date();
        for (Keymanage keymanage : keymanages) {
            KeyOperationRecord record = new KeyOperationRecord();
            record.setKeyId(keymanage.getKeyId());
            record.setUserId(keymanage.getUserId());
            record.setUserName(keymanage.getUserName());
            record.setKeyName(keymanage.getKeyName());
            record.setEncrytType(keymanage.getEncrytType());
            record.setEncrytName(keymanage.getEncrytName());
            record.setKeyVersion(keymanage.getVersion());
            record.setActionType(actionType);
            record.setActionSource(actionSource);
            record.setResultStatus("0");
            record.setChainStatus(keymanage.getChainStatus());
            applyProofFields(record, keymanage);
            record.setResultMessage(resultMessage);
            record.setReceiveStatus("0");
            record.setActionTime(actionTime);
            records.add(record);
        }
        for (List<KeyOperationRecord> chunk : chunks(records, 500)) {
            keyOperationRecordMapper.insertKeyOperationRecordBatch(chunk);
        }
    }

    @Transactional
    public void updateLatestResult(Long keyId, String actionType, String resultStatus, String chainStatus,
                                   String chainHash, Long blockHeight, String resultMessage) {
        keyOperationRecordMapper.updateLatestResult(keyId, actionType, resultStatus, chainStatus, chainHash, blockHeight, resultMessage);
    }

    public List<KeyOperationRecord> list(KeyOperationRecord query) {
        return keyOperationRecordMapper.selectKeyOperationRecordList(query);
    }

    public Optional<KeyOperationRecord> findById(Long recordId) {
        return Optional.ofNullable(keyOperationRecordMapper.selectKeyOperationRecordById(recordId));
    }

    public List<KeyOperationRecord> listBatchProofRecords(String batchId, String actionType) {
        if (batchId == null || batchId.trim().isEmpty()) {
            return new ArrayList<>();
        }
        String normalizedActionType = actionType == null || actionType.trim().isEmpty() ? "UPDATE" : actionType.trim();
        return keyOperationRecordMapper.selectBatchRecords(batchId, normalizedActionType);
    }

    public void refreshBatchProofWithRetry(String batchId, String actionType) {
        for (int attempt = 1; attempt <= BATCH_PROOF_REFRESH_RETRIES; attempt++) {
            try {
                refreshBatchProof(batchId, actionType);
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == BATCH_PROOF_REFRESH_RETRIES) {
                    log.warn("refresh batch proof failed after retries, batchId={}, actionType={}", batchId, actionType, ex);
                    return;
                }
                sleepBeforeRetry(attempt);
            }
        }
    }

    @Transactional
    public void refreshBatchProof(String batchId, String actionType) {
        if (batchId == null || batchId.trim().isEmpty()) {
            return;
        }
        List<KeyOperationRecord> records = keyOperationRecordMapper.selectBatchRecords(batchId, actionType);
        if (records == null || records.isEmpty()) {
            return;
        }

        int expectedCount = 0;
        for (KeyOperationRecord record : records) {
            if (record.getExpectedCount() != null && record.getExpectedCount() > expectedCount) {
                expectedCount = record.getExpectedCount();
            }
        }
        if (expectedCount <= 0) {
            expectedCount = records.size();
        }

        // 按 node_index 排序，保证叶子顺序稳定 → 根可复现
        records.sort((left, right) -> Integer.compare(
            left.getNodeIndex() == null ? 0 : left.getNodeIndex(),
            right.getNodeIndex() == null ? 0 : right.getNodeIndex()
        ));

        Map<Integer, KeyOperationRecord> byIndex = new LinkedHashMap<>();
        boolean duplicateIndex = false;
        for (KeyOperationRecord record : records) {
            Integer nodeIndex = record.getNodeIndex() == null ? byIndex.size() : record.getNodeIndex();
            if (byIndex.containsKey(nodeIndex)) {
                duplicateIndex = true;
            }
            byIndex.put(nodeIndex, record);
        }

        // 叶子值：优先 consistencyHash，其次 commitment。
        // 与早前实现相比，这里不再做「拼接后再哈希」，而是交给 MerkleTree。
        List<String> leafValues = new ArrayList<>(records.size());
        for (KeyOperationRecord record : records) {
            leafValues.add(valueOrDefault(record.getConsistencyHash(), record.getCommitment()));
        }
        MerkleTree tree = new MerkleTree(leafValues);
        String batchRoot = tree.getRoot();

        // 逐条写入 Merkle 证明路径，使每条记录可被独立验证
        for (int i = 0; i < records.size(); i++) {
            List<String> proof = tree.getProof(i);
            keyOperationRecordMapper.updateProofPath(records.get(i).getRecordId(), String.join("|", proof));
        }

        String verifyStatus;
        String verifyMessage;
        if (duplicateIndex) {
            verifyStatus = "2";
            verifyMessage = "node index duplicated";
        } else if (records.size() < expectedCount || !hasFullIndexRange(byIndex, expectedCount)) {
            verifyStatus = "0";
            verifyMessage = "waiting for leaf commitments " + records.size() + "/" + expectedCount;
        } else if (!verifyAllLeaves(tree, leafValues, records)) {
            // 自检：用生成的证明路径反算根，必须与 batchRoot 一致
            verifyStatus = "2";
            verifyMessage = "merkle self-check failed";
        } else {
            verifyStatus = "1";
            verifyMessage = "merkle proof verified (leaves=" + records.size() + ", root=" + shortHash(batchRoot) + ")";
        }

        keyOperationRecordMapper.updateBatchProof(batchId, actionType, batchRoot, verifyStatus, verifyMessage);
    }

    /**
     * 用每条记录各自的证明路径独立重算 Merkle 根并比对，作为写入前的自检。
     * <p>
     * 这一步是「证明可用」的保证：若证明路径与根不匹配，说明数据不一致或实现有误，
     * 此时不应把 verify_status 置为成功。复用同一棵树，避免重复构造。
     */
    private boolean verifyAllLeaves(MerkleTree tree, List<String> leafValues, List<KeyOperationRecord> records) {
        String batchRoot = tree.getRoot();
        for (int i = 0; i < leafValues.size(); i++) {
            List<String> proof = tree.getProof(i);
            if (!MerkleTree.verify(leafValues.get(i), proof, batchRoot)) {
                log.warn("Merkle 自检失败: recordId={}, batchRoot={}",
                    i < records.size() ? records.get(i).getRecordId() : null, batchRoot);
                return false;
            }
        }
        return true;
    }

    private String shortHash(String hash) {
        if (hash == null) {
            return "";
        }
        return hash.length() <= 16 ? hash : hash.substring(0, 16) + "...";
    }

    private void sleepBeforeRetry(int attempt) {
        try {
            Thread.sleep(BATCH_PROOF_REFRESH_BACKOFF_MS * attempt);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    @Transactional
    public void receive(Long recordId, Long userId) {
        KeyOperationRecord current = Optional.ofNullable(keyOperationRecordMapper.selectKeyOperationRecordById(recordId))
            .orElseThrow(() -> new IllegalStateException("操作记录不存在: " + recordId));
        if (!userId.equals(current.getUserId())) {
            throw new IllegalStateException("无权接收该结果记录");
        }
        if ("0".equals(current.getResultStatus())) {
            throw new IllegalStateException("当前结果仍在处理中，暂不可接收");
        }
        if ("1".equals(current.getReceiveStatus())) {
            return;
        }
        keyOperationRecordMapper.markReceived(recordId, userId);
    }

    public Map<String, Object> buildDashboardSummary() {
        LocalDate today = LocalDate.now();
        Date startTime = Date.from(today.minusDays(6).atStartOfDay(ZoneId.systemDefault()).toInstant());

        List<String> labels = new ArrayList<>();
        List<Integer> manualUpdateSeries = new ArrayList<>();
        List<Integer> autoUpdateSeries = new ArrayList<>();
        List<Integer> revokeSeries = new ArrayList<>();
        for (int i = 6; i >= 0; i--) {
            LocalDate day = today.minusDays(i);
            labels.add(day.toString());
            manualUpdateSeries.add(0);
            autoUpdateSeries.add(0);
            revokeSeries.add(0);
        }

        Map<String, Integer> operationDistribution = new LinkedHashMap<>();
        operationDistribution.put("手动更新", 0);
        operationDistribution.put("自动更新", 0);
        operationDistribution.put("密钥回收", 0);

        try {
            List<KeyOperationRecord> recentRecords = keyOperationRecordMapper.selectRecentDashboardRecordsSince(startTime);
            for (KeyOperationRecord record : recentRecords) {
                if (record.getActionTime() == null) {
                    continue;
                }
                LocalDate actionDate = record.getActionTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDate();
                int dayIndex = (int) (today.toEpochDay() - actionDate.toEpochDay());
                if (dayIndex < 0 || dayIndex >= 7) {
                    continue;
                }
                int seriesIndex = 6 - dayIndex;
                if ("UPDATE".equals(record.getActionType())) {
                    if ("AUTO".equals(record.getActionSource())) {
                        autoUpdateSeries.set(seriesIndex, autoUpdateSeries.get(seriesIndex) + 1);
                        operationDistribution.put("自动更新", operationDistribution.get("自动更新") + 1);
                    } else {
                        manualUpdateSeries.set(seriesIndex, manualUpdateSeries.get(seriesIndex) + 1);
                        operationDistribution.put("手动更新", operationDistribution.get("手动更新") + 1);
                    }
                } else if ("REVOKE".equals(record.getActionType())) {
                    revokeSeries.set(seriesIndex, revokeSeries.get(seriesIndex) + 1);
                    operationDistribution.put("密钥回收", operationDistribution.get("密钥回收") + 1);
                }
            }
        } catch (Exception ex) {
            log.error("Failed to build dashboard trend data", ex);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("totalUpdates", keyOperationRecordMapper.countByActionType("UPDATE"));
        payload.put("totalRevokes", keyOperationRecordMapper.countByActionType("REVOKE"));
        payload.put("autoUpdateEnabled", keymanageMapper.countAutoUpdateEnabled());
        payload.put("pendingReceives", keyOperationRecordMapper.countPendingReceives());
        payload.put("failedResults", keyOperationRecordMapper.countFailedResults());
        payload.put("recent7Days", buildRecentSeries(labels, manualUpdateSeries, autoUpdateSeries, revokeSeries));
        payload.put("operationDistribution", operationDistribution);
        return payload;
    }

    private Map<String, Object> buildRecentSeries(List<String> labels, List<Integer> manualUpdateSeries,
                                                  List<Integer> autoUpdateSeries, List<Integer> revokeSeries) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("labels", labels);
        data.put("manualUpdate", manualUpdateSeries);
        data.put("autoUpdate", autoUpdateSeries);
        data.put("revoke", revokeSeries);
        return data;
    }

    private void applyProofFields(KeyOperationRecord record, Keymanage keymanage) {
        record.setBatchId(keymanage.getBatchId());
        record.setParentBatchId(keymanage.getParentBatchId());
        record.setRootBatchId(keymanage.getRootBatchId());
        record.setTreePath(keymanage.getTreePath());
        record.setTreeLevel(keymanage.getTreeLevel());
        record.setNodeIndex(keymanage.getNodeIndex());
        record.setExpectedCount(keymanage.getExpectedCount());
        record.setTreeFanout(keymanage.getTreeFanout());
        record.setProofMode(keymanage.getProofMode());
        record.setCommitment(keymanage.getCommitment());
        record.setConsistencyHash(keymanage.getConsistencyHash());
        record.setBatchRoot(keymanage.getBatchRoot());
        record.setVerifyStatus(keymanage.getVerifyStatus());
        record.setVerifyMessage(keymanage.getVerifyMessage());
    }

    private boolean hasFullIndexRange(Map<Integer, KeyOperationRecord> recordsByIndex, int expectedCount) {
        for (int i = 0; i < expectedCount; i++) {
            if (!recordsByIndex.containsKey(i)) {
                return false;
            }
        }
        return true;
    }

    private String valueOrDefault(String candidate, String fallback) {
        return candidate == null || candidate.trim().isEmpty() ? fallback : candidate;
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(bytes.length * 2);
            for (byte current : bytes) {
                builder.append(String.format("%02x", current));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 digest unavailable", ex);
        }
    }

    private <T> List<List<T>> chunks(List<T> source, int batchSize) {
        List<List<T>> result = new ArrayList<>();
        if (source == null || source.isEmpty()) {
            return result;
        }
        int size = batchSize <= 0 ? 500 : batchSize;
        for (int i = 0; i < source.size(); i += size) {
            result.add(source.subList(i, Math.min(i + size, source.size())));
        }
        return result;
    }
}
