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
