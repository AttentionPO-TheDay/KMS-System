package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.mapping.ParameterMapping;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

/** Export the actual MyBatis prepared statements for a temporary-table MySQL verification. */
class RotationMapperSqlTest {
    @Test void batchSqlMapsAllRowsAndMetadataContainsNoMaterial() throws Exception {
        Configuration cfg = new Configuration();
        String resource = "mapper/updatedel/KeymanageMapper.xml";
        try (InputStream in = getClass().getClassLoader().getResourceAsStream(resource)) {
            new XMLMapperBuilder(in, cfg, resource, cfg.getSqlFragments()).parse();
        }
        List<Keymanage> keys = new ArrayList<>();
        for (long id = 1; id <= 2; id++) {
            Keymanage key = new Keymanage(); key.setKeyId(id); key.setUserId(1L);
            key.setUserName("rotation-sql-test"); key.setEncrytName("SM2"); key.setEncrytType("test");
            key.setUa("public-ua"); key.setKeyValue("new-material-" + id);
            key.setVersion(2); key.setStatus("0"); key.setKeyDomain("acceptance");
            key.setAutoUpdate("0"); key.setKeyName("test"); key.setKeyUse("test");
            key.setCreTime("2026-10-21 00:00:00"); key.setUpdTime("2026-10-21 01:00:00");
            key.setMsKeyId("test"); key.setAlgorithmVersion("v1"); key.setKeyMaterialState("ACTIVE");
            keys.add(key);
        }
        Map<String, Object> params = new HashMap<>(); params.put("keys", keys);
        params.put("keyIds", Arrays.asList(1L, 2L)); params.put("userName", "rotation-sql-test");
        List<Map<String, Object>> statements = new ArrayList<>();
        for (String name : Arrays.asList("selectRotationCandidates", "archiveRotationBatch", "rotateBatch", "selectMetadataByIds")) {
            if (name.equals("rotateBatch")) {
                JdbcTemplate jdbc = mock(JdbcTemplate.class);
                when(jdbc.update(anyString(), org.mockito.ArgumentMatchers.<Object[]>any())).thenAnswer(call -> {
                    Object[] values = Arrays.copyOfRange(call.getArguments(), 1, call.getArguments().length);
                    assertEquals(1, values.length);
                    List<List<Object>> data = new ObjectMapper().readValue((String) values[0], List.class);
                    assertEquals(keys.size(), data.size());
                    assertEquals(18, data.get(0).size());
                    Map<String, Object> stmt = new LinkedHashMap<>(); stmt.put("name", name);
                    stmt.put("sql", call.getArgument(0)); stmt.put("args", values); statements.add(stmt);
                    return keys.size();
                });
                assertEquals(keys.size(), RotationBatchWriter.rotate(jdbc, keys));
                continue;
            }
            BoundSql bound = cfg.getMappedStatement("com.ruoyi.updatedel.mapper.KeymanageMapper." + name).getBoundSql(params);
            List<Object> args = new ArrayList<>();
            for (ParameterMapping mapping : bound.getParameterMappings()) {
                String property = mapping.getProperty();
                args.add(bound.hasAdditionalParameter(property) ? bound.getAdditionalParameter(property) : cfg.newMetaObject(params).getValue(property));
            }
            Map<String, Object> stmt = new LinkedHashMap<>(); stmt.put("name", name);
            stmt.put("sql", bound.getSql()); stmt.put("args", args); statements.add(stmt);
            if (name.equals("selectMetadataByIds")) {
                assertFalse(bound.getSql().contains(" ua"));
                assertTrue(bound.getSql().contains("sha2(key_value, 256)"));
            }
        }
        String auditResource = "mapper/updatedel/KeyOperationRecordMapper.xml";
        try (InputStream in = getClass().getClassLoader().getResourceAsStream(auditResource)) {
            new XMLMapperBuilder(in, cfg, auditResource, cfg.getSqlFragments()).parse();
        }
        List<KeyOperationRecord> records = new ArrayList<>();
        for (Keymanage key : keys) {
            KeyOperationRecord record = new KeyOperationRecord();
            record.setKeyId(key.getKeyId()); record.setUserName(key.getUserName()); record.setUserId(key.getUserId());
            record.setKeyName("quoted ' audit " + key.getKeyId()); record.setKeyVersion(key.getVersion());
            record.setActionType("UPDATE"); record.setActionSource("MANUAL");
            record.setResultStatus("0"); record.setChainStatus("0"); record.setReceiveStatus("0");
            record.setBatchId("rotation-sql-" + key.getKeyId()); record.setTreePath("path/" + key.getKeyId());
            record.setCommitment("test-commitment"); record.setExpectedCount(1); record.setNodeIndex(0);
            record.setVerifyStatus("0"); record.setResultMessage("pending");
            record.setActionTime(java.sql.Timestamp.valueOf("2026-10-21 01:02:03"));
            records.add(record);
        }
        Map<String, Object> auditParams = Collections.singletonMap("records", records);
        BoundSql auditSql = cfg.getMappedStatement("com.ruoyi.updatedel.mapper.KeyOperationRecordMapper.insertKeyOperationRecordBatch").getBoundSql(auditParams);
        List<Object> expected = new ArrayList<>();
        for (ParameterMapping mapping : auditSql.getParameterMappings()) {
            Object value = auditSql.getAdditionalParameter(mapping.getProperty());
            expected.add(value instanceof Date ? new java.sql.Timestamp(((Date) value).getTime()).toString() : value);
        }
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.update(anyString(), org.mockito.ArgumentMatchers.<Object[]>any())).thenAnswer(call -> {
            Object[] values = Arrays.copyOfRange(call.getArguments(), 1, call.getArguments().length);
            assertEquals(1, values.length);
            List<List<Object>> data = new ObjectMapper().readValue((String) values[0], List.class);
            List<Object> actual = new ArrayList<>();
            for (List<Object> row : data) actual.addAll(row);
            // JSON numbers preserve value; normalize the old mapper's Long/Integer wrappers.
            assertEquals(new ObjectMapper().writeValueAsString(expected), new ObjectMapper().writeValueAsString(actual));
            Map<String, Object> stmt = new LinkedHashMap<>(); stmt.put("name", "insertAudit");
            stmt.put("sql", call.getArgument(0)); stmt.put("args", values); statements.add(stmt);
            return records.size();
        });
        assertEquals(records.size(), RotationBatchWriter.insertAudit(jdbc, records));
        Files.write(Paths.get("target/rotation-sql-fixture.json"), new ObjectMapper().writeValueAsBytes(statements));
    }
}
