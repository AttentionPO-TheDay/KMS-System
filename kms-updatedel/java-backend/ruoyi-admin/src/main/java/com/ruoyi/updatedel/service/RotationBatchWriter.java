package com.ruoyi.updatedel.service;

import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

/** MySQL 8 JSON_TABLE keeps the prepared SQL constant and binds one document per batch. */
final class RotationBatchWriter {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String[] KEY_COLUMNS = ("key_id,user_id,user_name,ua,encryt_type,encryt_name,"
        + "key_name,key_use,key_value,cre_time,upd_time,auto_update,status,version,key_domain,"
        + "ms_key_id,algorithm_version,key_material_state").split(",");
    private static final String AUDIT_COLUMNS = "key_id,user_id,user_name,key_name,encryt_type,encryt_name,key_version,"
        + "action_type,action_source,result_status,chain_status,chain_hash,block_height,"
        + "batch_id,parent_batch_id,root_batch_id,tree_path,tree_level,node_index,expected_count,"
        + "tree_fanout,proof_mode,commitment,consistency_hash,batch_root,proof_path,verify_status,verify_message,"
        + "result_message,receive_status,action_time,receive_time,create_time,update_time";

    private RotationBatchWriter() {}

    static int rotate(JdbcTemplate jdbc, List<Keymanage> keys) {
        StringBuilder sql = new StringBuilder("update keymanage k join ")
            .append(table(KEY_COLUMNS)).append(" on k.key_id=v.key_id set ");
        for (int i = 1; i < KEY_COLUMNS.length; i++) {
            if (i > 1) sql.append(',');
            sql.append("k.").append(KEY_COLUMNS[i]).append("=v.").append(KEY_COLUMNS[i]);
        }
        sql.append(",k.chain_status='0',k.chain_hash=null,k.block_height=null");
        List<List<Object>> rows = new ArrayList<>(keys.size());
        for (Keymanage key : keys) {
            rows.add(Arrays.asList(key.getKeyId(), key.getUserId(), key.getUserName(), key.getUa(),
                key.getEncrytType(), key.getEncrytName(), key.getKeyName(), key.getKeyUse(), key.getKeyValue(),
                key.getCreTime(), key.getUpdTime(), key.getAutoUpdate(), key.getStatus(), key.getVersion(),
                key.getKeyDomain(), key.getMsKeyId(), key.getAlgorithmVersion(), key.getKeyMaterialState()));
        }
        return jdbc.update(sql.toString(), encode(rows));
    }

    static int insertAudit(JdbcTemplate jdbc, List<KeyOperationRecord> records) {
        String[] columns = AUDIT_COLUMNS.substring(0, AUDIT_COLUMNS.indexOf(",create_time")).split(",");
        String sql = "insert into key_operation_record (" + AUDIT_COLUMNS + ") select "
            + String.join(",", columns) + ",now(),now() from " + table(columns);
        List<List<Object>> rows = new ArrayList<>(records.size());
        for (KeyOperationRecord r : records) {
            rows.add(Arrays.asList(r.getKeyId(), r.getUserId(), r.getUserName(), r.getKeyName(),
                r.getEncrytType(), r.getEncrytName(), r.getKeyVersion(), r.getActionType(), r.getActionSource(),
                r.getResultStatus(), r.getChainStatus(), r.getChainHash(), r.getBlockHeight(), r.getBatchId(),
                r.getParentBatchId(), r.getRootBatchId(), r.getTreePath(), r.getTreeLevel(), r.getNodeIndex(),
                r.getExpectedCount(), r.getTreeFanout(), r.getProofMode(), r.getCommitment(), r.getConsistencyHash(),
                r.getBatchRoot(), r.getProofPath(), r.getVerifyStatus(), r.getVerifyMessage(), r.getResultMessage(),
                r.getReceiveStatus(), timestamp(r.getActionTime()), timestamp(r.getReceiveTime())));
        }
        return jdbc.update(sql, encode(rows));
    }

    private static String table(String[] columns) {
        StringBuilder sql = new StringBuilder("json_table(?, '$[*]' columns (");
        for (int i = 0; i < columns.length; i++) {
            if (i > 0) sql.append(',');
            String c = columns[i];
            String type = "longtext";
            if (Arrays.asList("key_id", "user_id", "block_height").contains(c)) type = "bigint";
            if (Arrays.asList("version", "key_version", "tree_level", "node_index", "expected_count", "tree_fanout").contains(c)) type = "int";
            if (Arrays.asList("action_time", "receive_time").contains(c)) type = "datetime";
            sql.append(c).append(' ').append(type).append(" path '$[").append(i).append("]' error on error");
        }
        return sql.append(")) v").toString();
    }

    private static String timestamp(java.util.Date date) {
        return date == null ? null : new java.sql.Timestamp(date.getTime()).toString();
    }

    private static String encode(List<List<Object>> rows) {
        try {
            return JSON.writeValueAsString(rows);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("rotation batch serialization failed", ex);
        }
    }
}
