package com.ruoyi.generate.service.impl;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class GenerateChainBackendBoundaryTest {
    @Test
    void pausedWritePreservesConfirmedEvidenceWithoutCallbacks() {
        GenerateChainServiceImpl service = new GenerateChainServiceImpl();
        GenerateKeyService keys = mock(GenerateKeyService.class);
        @SuppressWarnings("unchecked") KafkaTemplate<String, String> kafka = mock(KafkaTemplate.class);
        ReflectionTestUtils.setField(service, "generateKeyService", keys);
        ReflectionTestUtils.setField(service, "kafkaTemplate", kafka);
        Keymanage key = new Keymanage();
        key.setKeyId(42L);
        key.setChainStatus("1");
        key.setChainHash("previous-confirmed-hash");
        key.setBlockHeight(123L);
        key.setKeyValue("not-json");
        assertFalse(service.isChainWriteEnabled());
        assertFalse(service.processChainSync(key));
        assertEquals("1", key.getChainStatus());
        assertEquals("previous-confirmed-hash", key.getChainHash());
        assertEquals(Long.valueOf(123), key.getBlockHeight());
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verifyNoInteractions(keys, kafka);
    }

    @Test
    void pauseBlocksExistingWrapperBeforeCacheLookup() throws Exception {
        GenerateChainServiceImpl service = new GenerateChainServiceImpl();
        Class<?> type = Class.forName(GenerateChainServiceImpl.class.getName() + "$FiscoBcosWrapper");
        Object wrapper = mock(type);
        ReflectionTestUtils.setField(service, "fiscoWrapper", wrapper);
        Method ensure = GenerateChainServiceImpl.class.getDeclaredMethod("ensureFiscoWrapper");
        ensure.setAccessible(true);
        assertEquals(Boolean.FALSE, ensure.invoke(service));
        verifyNoInteractions(wrapper);
    }

    @Test
    void listenerRequiresBothFlagsAndDefaultsOff() throws Exception {
        Method method = com.ruoyi.generate.consumer.ChainTaskConsumer.class.getMethod("onMessage", java.util.List.class);
        String expression = method.getAnnotation(org.springframework.kafka.annotation.KafkaListener.class).autoStartup();
        assertListenerFlags(expression, false, false, false);
        assertListenerFlags(expression, true, false, false);
        assertListenerFlags(expression, false, true, false);
        assertListenerFlags(expression, true, true, true);
    }

    private void assertListenerFlags(String template, boolean writes, boolean consumer, boolean expected) {
        String expression = template.replace("${KMS_CHAIN_WRITES_ENABLED:false}", String.valueOf(writes))
            .replace("${KMS_CHAIN_CONSUMER_ENABLED:false}", String.valueOf(consumer));
        Boolean actual = new org.springframework.expression.spel.standard.SpelExpressionParser()
            .parseExpression(expression, new org.springframework.expression.common.TemplateParserContext())
            .getValue(Boolean.class);
        assertEquals(expected, actual);
    }

    @Test
    void enablingWritesAloneDoesNotConsumeOrAuditOldQueue() {
        com.ruoyi.generate.consumer.ChainTaskConsumer consumer = new com.ruoyi.generate.consumer.ChainTaskConsumer();
        com.ruoyi.generate.service.GenerateChainService chain = mock(com.ruoyi.generate.service.GenerateChainService.class);
        com.ruoyi.generate.audit.GenerateAuditService audit = mock(com.ruoyi.generate.audit.GenerateAuditService.class);
        ReflectionTestUtils.setField(consumer, "generateChainService", chain);
        ReflectionTestUtils.setField(consumer, "auditService", audit);
        ReflectionTestUtils.setField(consumer, "chainWritesEnabled", true);
        consumer.onMessage(null);
        verifyNoInteractions(chain, audit);
    }

    @Test
    void defaultDoesNotInitializeSdk() {
        GenerateChainServiceImpl service = new GenerateChainServiceImpl();
        service.init();
        assertFalse(service.isFabricDidBackend());
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
    }

    @Test
    void unknownBackendIsNotLegacyFallback() {
        GenerateChainServiceImpl service = new GenerateChainServiceImpl();
        ReflectionTestUtils.setField(service, "chainBackend", "fabric-typo");
        assertThrows(IllegalStateException.class, service::init);
    }

    @Test
    void fabricStopsBeforeCalculatingPublicMaterialOrInitializingSdk() throws Exception {
        GenerateChainServiceImpl service = new GenerateChainServiceImpl();
        GenerateKeyService keys = mock(GenerateKeyService.class);
        @SuppressWarnings("unchecked") KafkaTemplate<String, String> kafka = mock(KafkaTemplate.class);
        ReflectionTestUtils.setField(service, "generateKeyService", keys);
        ReflectionTestUtils.setField(service, "kafkaTemplate", kafka);
        ReflectionTestUtils.setField(service, "chainResultTopic", "offline-results");
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        ReflectionTestUtils.setField(service, "chainBackend", "fabric-did");
        ReflectionTestUtils.setField(service, "fabricChainId", "offline-test-chain");
        Keymanage key = new Keymanage();
        key.setKeyId(42L);
        assertFalse(service.processChainSync(key));
        assertNull(ReflectionTestUtils.getField(service, "fiscoWrapper"));
        verify(keys).updateChainStatus(eq(42L), eq("2"), isNull(), isNull());
        ArgumentCaptor<String> payload = ArgumentCaptor.forClass(String.class);
        verify(kafka).send(eq("offline-results"), eq("42"), payload.capture());
        assertEquals("FABRIC_DID", JSON.parseObject(payload.getValue()).getString("provider"));
        assertEquals("offline-test-chain", JSON.parseObject(payload.getValue()).getString("chain_id"));
        assertEquals("UNSUPPORTED_LEGACY_KEY_MODEL_FOR_DID", JSON.parseObject(payload.getValue()).getString("error_message"));
        Method ensure = GenerateChainServiceImpl.class.getDeclaredMethod("ensureFiscoWrapper");
        ensure.setAccessible(true);
        assertEquals(Boolean.FALSE, ensure.invoke(service));
    }
}
