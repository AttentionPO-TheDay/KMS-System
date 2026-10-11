package com.ruoyi.updatedel.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.mapper.AutoUpdateRecordMapper;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import com.ruoyi.updatedel.service.generator.EccKeyGenerator;
import com.ruoyi.updatedel.service.generator.SsclKeyGenerator;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Collections;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AutoUpdateGuardsTest {
    private KeymanageMapper keymanageMapper;
    private LifecycleService lifecycleService;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        keymanageMapper = mock(KeymanageMapper.class);
        lifecycleService = new LifecycleService(
            keymanageMapper,
            mock(EccKeyGenerator.class),
            mock(SsclKeyGenerator.class),
            (KafkaTemplate<String, String>) mock(KafkaTemplate.class),
            new ObjectMapper(),
            mock(KeyOperationRecordService.class),
            mock(JdbcTemplate.class));
    }

    @Test
    void unsupportedEnabledStateCanBeRepeatedOrClosedButCannotBeOpened() {
        Keymanage current = key("KYBER-768", "1");
        when(keymanageMapper.selectkeymanageByKeyId(7L)).thenReturn(current);

        assertDoesNotThrow(() -> lifecycleService.updateAutoUpdate(7L, "1"));
        verify(keymanageMapper).updateAutoUpdate(7L, "1");

        reset(keymanageMapper);
        when(keymanageMapper.selectkeymanageByKeyId(7L)).thenReturn(current);
        assertDoesNotThrow(() -> lifecycleService.updateAutoUpdate(7L, "0"));
        verify(keymanageMapper).updateAutoUpdate(7L, "0");

        reset(keymanageMapper);
        current.setAutoUpdate("0");
        when(keymanageMapper.selectkeymanageByKeyId(7L)).thenReturn(current);
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> lifecycleService.updateAutoUpdate(7L, "true"));
        assertTrue(error.getMessage().contains("KYBER"));
    }

    @Test
    void createAndRotatePathsRejectUnsupportedEnableTransitions() {
        Keymanage create = key("FALCON-512", "1");
        create.setKeyId(8L);
        IllegalStateException createError = assertThrows(
            IllegalStateException.class,
            () -> lifecycleService.createKey(create));
        assertTrue(createError.getMessage().contains("FALCON"));

        Keymanage current = key("FALCON-512", "0");
        current.setKeyId(9L);
        when(keymanageMapper.selectkeymanageByKeyId(9L)).thenReturn(current);
        Keymanage request = new Keymanage();
        request.setKeyId(9L);
        request.setRotate(true);
        request.setAutoUpdate("1");
        IllegalStateException rotateError = assertThrows(
            IllegalStateException.class,
            () -> lifecycleService.rotateKey(request));
        assertTrue(rotateError.getMessage().contains("FALCON"));
    }

    @Test
    void latestQueriesCarryOwnerScopeAndExecutionIsSerialized() throws Exception {
        AutoUpdateRecordMapper records = mock(AutoUpdateRecordMapper.class);
        AutoUpdateRunService service = new AutoUpdateRunService(
            records, mock(KeymanageMapper.class), mock(LifecycleService.class));
        when(records.selectLatestItemsByKeyIds(anyList(), eq(42L)))
            .thenReturn(Collections.emptyList());
        when(records.selectLatestItemsByKeyIds(anyList(), eq((Long) null)))
            .thenReturn(Collections.emptyList());

        assertEquals(Collections.emptyList(), service.latestByKeyIds(Arrays.asList(11L, 11L), 42L));
        verify(records).selectLatestItemsByKeyIds(eq(Arrays.asList(11L)), eq(42L));
        assertEquals(Collections.emptyList(), service.latestByKeyIds(Arrays.asList(11L), null));
        verify(records).selectLatestItemsByKeyIds(eq(Arrays.asList(11L)), eq((Long) null));

        assertTrue(Modifier.isSynchronized(
            AutoUpdateRunService.class.getMethod("executeOnce", String.class).getModifiers()));
    }

    private Keymanage key(String algorithm, String autoUpdate) {
        Keymanage key = new Keymanage();
        key.setKeyId(7L);
        key.setEncrytName(algorithm);
        key.setAutoUpdate(autoUpdate);
        key.setStatus("0");
        return key;
    }
}
