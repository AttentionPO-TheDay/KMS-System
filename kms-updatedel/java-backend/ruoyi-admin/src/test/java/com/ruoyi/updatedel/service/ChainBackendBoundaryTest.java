package com.ruoyi.updatedel.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import java.lang.reflect.Method;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** 只用 mock；不得因测试“禁止旧链”而真的实例化 SDK/连 RPC。 */
class ChainBackendBoundaryTest {
    private KeymanageMapper mapper;
    private KafkaTemplate<String, String> kafka;
    private KeyOperationRecordService records;
    private UpdatedelChainService service;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setup() {
        mapper = mock(KeymanageMapper.class);
        kafka = mock(KafkaTemplate.class);
        records = mock(KeyOperationRecordService.class);
        service = new UpdatedelChainService(mapper, kafka, records);
        ReflectionTestUtils.setField(service, "chainResultTopic", "offline-chain-results");
    }

    @Test
    void pausedMutationsPreserveEvidenceAndLocalResults() {
        Keymanage key = new Keymanage();
        key.setKeyId(42L);
        key.setChainStatus("1");
        key.setChainHash("previous-confirmed-hash");
        key.setBlockHeight(123L);
        key.setKeyValue("not-json");
        assertFalse(service.isChainWriteEnabled());
        assertFalse(service.processCreateChainSync(key));
        assertFalse(service.processRotateChainSync(key));
        assertFalse(service.processRevokeChainSync(key));
        assertNull(service.recordLifecycleEvent("KEY_DISTRIBUTED", 42, 1, "offline", "hash"));
        assertEquals("1", key.getChainStatus());
        assertEquals("previous-confirmed-hash", key.getChainHash());
        assertEquals(Long.valueOf(123), key.getBlockHeight());
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verifyNoInteractions(mapper, kafka, records);
    }

    @Test
    void globalAndLegacyPauseBlockEvenCachedWrapper() throws Exception {
        Class<?> type = Class.forName(UpdatedelChainService.class.getName() + "$FiscoBcosWrapper");
        Object wrapper = mock(type);
        ReflectionTestUtils.setField(service, "fiscoWrapper", wrapper);
        Method ensure = UpdatedelChainService.class.getDeclaredMethod("ensureFiscoWrapper");
        ensure.setAccessible(true);
        assertEquals(Boolean.FALSE, ensure.invoke(service));
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        ReflectionTestUtils.setField(service, "chainSyncEnabled", false);
        assertFalse(service.isChainWriteEnabled());
        assertEquals(Boolean.FALSE, ensure.invoke(service));
        assertNull(service.recordLifecycleEvent("KEY_DISTRIBUTED", 42, 1, "offline", "hash"));
        verifyNoInteractions(wrapper, mapper, kafka, records);
    }

    @Test
    @SuppressWarnings("unchecked")
    void directEndpointReportsPauseBeforeParsingOrCallingChain() {
        com.ruoyi.updatedel.controller.InternalLifecycleController controller =
            new com.ruoyi.updatedel.controller.InternalLifecycleController(null, records, null, null, null, null, service, null, null);
        ReflectionTestUtils.setField(controller, "internalToken", "offline-test-token");
        java.util.Map<String, Object> payload = controller.chainEvent("offline-test-token", null);
        assertEquals(409, payload.get("code"));
        java.util.Map<String, Object> data = (java.util.Map<String, Object>) payload.get("data");
        assertEquals("PAUSED", data.get("status"));
        assertEquals("CHAIN_WRITES_PAUSED", data.get("errorCode"));
        assertEquals("LEGACY_FISCO", data.get("provider"));
        assertFalse(data.containsKey("chainHash"));
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verifyNoInteractions(mapper, kafka, records);
    }

    @Test
    void listenerRequiresBothFlagsAndPreservesQueueWhenConsumerNotEnabled() throws Exception {
        Method method = com.ruoyi.updatedel.consumer.UpdatedelChainConsumer.class.getMethod("onMessage", java.util.List.class);
        String template = method.getAnnotation(org.springframework.kafka.annotation.KafkaListener.class).autoStartup();
        for (boolean writes : new boolean[] {false, true}) {
            for (boolean consumerEnabled : new boolean[] {false, true}) {
                for (boolean legacy : new boolean[] {false, true}) {
                    String expression = template.replace("${KMS_CHAIN_WRITES_ENABLED:false}", String.valueOf(writes))
                        .replace("${KMS_CHAIN_CONSUMER_ENABLED:false}", String.valueOf(consumerEnabled))
                        .replace("${kms.lifecycle.chain-sync-enabled:true}", String.valueOf(legacy));
                    Boolean actual = new org.springframework.expression.spel.standard.SpelExpressionParser()
                        .parseExpression(expression, new org.springframework.expression.common.TemplateParserContext())
                        .getValue(Boolean.class);
                    assertEquals(writes && consumerEnabled && legacy, actual);
                }
            }
        }
        UpdatedelChainService chain = mock(UpdatedelChainService.class);
        com.ruoyi.updatedel.consumer.UpdatedelChainConsumer consumer =
            new com.ruoyi.updatedel.consumer.UpdatedelChainConsumer(chain, 1, 1, 1);
        try {
            ReflectionTestUtils.setField(consumer, "chainWritesEnabled", true);
            consumer.onMessage(null);
            verifyNoInteractions(chain);
        } finally {
            consumer.shutdown();
        }
    }

    @Test
    void defaultIsLegacyWithoutInitializingSdk() {
        service.init();
        assertFalse(service.isFabricDidBackend());
        assertEquals("LEGACY_FISCO", service.getChainProvider());
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verifyNoInteractions(mapper, kafka, records);
    }

    @Test
    void malformedSelectionDoesNotFallback() {
        ReflectionTestUtils.setField(service, "chainBackend", "fabrci-did");
        assertThrows(IllegalStateException.class, service::init);
        verifyNoInteractions(mapper, kafka, records);
    }

    @Test
    void fabricBlocksEvenAnExistingCachedWrapper() throws Exception {
        Class<?> wrapperType = Class.forName(UpdatedelChainService.class.getName() + "$FiscoBcosWrapper");
        ReflectionTestUtils.setField(service, "fiscoWrapper", mock(wrapperType));
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        ReflectionTestUtils.setField(service, "chainBackend", "fabric-did");
        Method ensure = UpdatedelChainService.class.getDeclaredMethod("ensureFiscoWrapper");
        ensure.setAccessible(true);
        assertEquals(Boolean.FALSE, ensure.invoke(service));
    }

    @Test
    void digestOnlyEventDoesNotClaimDidConfirmation() {
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        ReflectionTestUtils.setField(service, "chainBackend", "fabric-did");
        assertNull(service.recordLifecycleEvent("KEY_UPDATED", 42, 2, "Node-offline", "public-hash"));
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verifyNoInteractions(mapper, kafka, records);
    }

    @Test
    void threeLegacyMutationsAreExplicitlyUnsupportedAndScoped() {
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        ReflectionTestUtils.setField(service, "chainBackend", "fabric-did");
        ReflectionTestUtils.setField(service, "fabricChainId", "offline-test-chain");
        Keymanage key = new Keymanage();
        key.setKeyId(42L);
        assertFalse(service.processCreateChainSync(key));
        assertFalse(service.processRotateChainSync(key));
        assertFalse(service.processRevokeChainSync(key));
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verify(mapper, times(3)).updateChainStatus(eq(42L), eq("2"), isNull(), isNull());
        ArgumentCaptor<String> payloads = ArgumentCaptor.forClass(String.class);
        verify(kafka, times(3)).send(eq("offline-chain-results"), eq("42"), payloads.capture());
        for (String payload : payloads.getAllValues()) {
            JSONObject record = JSON.parseObject(payload);
            assertEquals("FABRIC_DID", record.getString("provider"));
            assertEquals("offline-test-chain", record.getString("chain_id"));
            assertEquals("2", record.getString("chain_status"));
            assertNull(record.get("chain_hash"));
            assertEquals("UNSUPPORTED_LEGACY_KEY_MODEL_FOR_DID", record.getString("error_message"));
        }
        verifyNoInteractions(records);
    }
}
