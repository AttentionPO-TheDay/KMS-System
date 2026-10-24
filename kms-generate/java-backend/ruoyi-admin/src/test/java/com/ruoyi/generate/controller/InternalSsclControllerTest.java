package com.ruoyi.generate.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.PartialKey;
import com.ruoyi.generate.domain.UserIdentity;
import com.ruoyi.generate.service.generator.SSCLGenerator;
import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.Map;
import org.bouncycastle.jce.ECNamedCurveTable;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class InternalSsclControllerTest {
    private SSCLGenerator generator;
    private InternalSsclController controller;
    private Map<String, Object> request;
    private final String identity = "ext-" + new String(new char[60]).replace('\0', 'a');

    @BeforeEach void setup() {
        generator = mock(SSCLGenerator.class);
        controller = new InternalSsclController(generator);
        ReflectionTestUtils.setField(controller, "internalToken", "offline-internal-token");
        request = new LinkedHashMap<>();
        request.put("identity", identity);
        request.put("ua", org.bouncycastle.util.encoders.Hex.toHexString(ECNamedCurveTable.getParameterSpec("sm2p256v1").getG().getEncoded(false)));
    }

    @Test void requiresInternalAuthenticationBeforeGenerating() {
        assertEquals(403, controller.partial(null, request).get("code"));
        assertEquals(403, controller.partial("wrong", request).get("code"));
        verifyNoInteractions(generator);
    }

    @Test void returnsOnlyShareAndPublicParametersInExactHexEncoding() {
        PartialKey share = new PartialKey();
        share.setMx(BigInteger.valueOf(11)); share.setMy(BigInteger.valueOf(282));
        when(generator.genPartialKey(any(UserIdentity.class), anyString())).thenReturn(share);
        ComParam params = new ComParam();
        params.setPPub(ECNamedCurveTable.getParameterSpec("sm2p256v1").getG());
        params.setxIndex(new BigInteger[]{BigInteger.ONE});
        params.setyIndex(new BigInteger[]{BigInteger.TEN});
        when(generator.getComParam()).thenReturn(params);
        AjaxResult result = controller.partial("offline-internal-token", request);
        assertEquals(200, result.get("code"));
        Map<?, ?> data = (Map<?, ?>) result.get("data");
        assertEquals(identity, data.get("identity"));
        assertTrue(((String) data.get("SSCLKey")).matches("04[0-9a-f]{128}"));
        assertTrue(((String) data.get("PPub")).matches("04[0-9a-f]{128}"));
        assertFalse(data.containsKey("SSCLEA"));
        assertFalse(data.containsKey("privateKey"));
        verify(generator).genPartialKey(argThat(user -> identity.equals(user.getIdentityData())), eq((String) request.get("ua")));
    }

    @Test void rejectsUnscopedIdentityAndUnknownFieldsBeforeGeneration() {
        request.put("identity", "A");
        assertEquals(400, controller.partial("offline-internal-token", request).get("code"));
        request.put("identity", identity); request.put("privateKey", "unexpected");
        assertEquals(400, controller.partial("offline-internal-token", request).get("code"));
        verifyNoInteractions(generator);
    }

    @Test void emptyServerTokenFailsClosed() {
        ReflectionTestUtils.setField(controller, "internalToken", "");
        assertEquals(403, controller.partial("", request).get("code"));
        verifyNoInteractions(generator);
    }

    @Test void realSsclGeneratorIsDeterministicUnderParallelCallsAndExportsInteroperabilityFixture() throws Exception {
        Class<?> secrets = com.ruoyi.common.crypto.KgcMasterSecret.class;
        Object originalSecrets = ReflectionTestUtils.getField(secrets, "secrets");
        Object originalId = ReflectionTestUtils.getField(secrets, "activeId");
        ReflectionTestUtils.setField(secrets, "secrets", java.util.Collections.singletonMap("offline-sscl", String.format("%064x", BigInteger.valueOf(19))));
        ReflectionTestUtils.setField(secrets, "activeId", "offline-sscl");
        java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(4);
        try {
            SSCLGenerator real = new SSCLGenerator();
            InternalSsclController endpoint = new InternalSsclController(real);
            ReflectionTestUtils.setField(endpoint, "internalToken", "offline-internal-token");
            String u = String.format("%064x", BigInteger.valueOf(9));
            String ua = org.bouncycastle.util.encoders.Hex.toHexString(ECNamedCurveTable.getParameterSpec("sm2p256v1").getG().multiply(BigInteger.valueOf(9)).getEncoded(false));
            request.put("ua", ua);
            Map<?, ?> expected = (Map<?, ?>) endpoint.partial("offline-internal-token", request).get("data");
            java.util.List<java.util.concurrent.Future<Map<?, ?>>> tasks = new java.util.ArrayList<>();
            for (int i = 0; i < 24; i++) tasks.add(pool.submit(() -> (Map<?, ?>) endpoint.partial("offline-internal-token", request).get("data")));
            for (java.util.concurrent.Future<Map<?, ?>> task : tasks) assertEquals(expected, task.get());
            BigInteger x = new BigInteger(((String) expected.get("SSCLKey")).substring(2, 66), 16);
            BigInteger n = ECNamedCurveTable.getParameterSpec("sm2p256v1").getN();
            BigInteger d = BigInteger.valueOf(9).add(real.getEA().multiply(x)).mod(n);
            Map<String, Object> sample = new LinkedHashMap<>();
            sample.put("clientSecret", u); sample.put("share", expected);
            sample.put("expectedPrivate", String.format("%064x", d));
            sample.put("expectedPublic", org.bouncycastle.util.encoders.Hex.toHexString(real.getComParam().getPPub().multiply(d).getEncoded(false)));
            java.nio.file.Files.write(java.nio.file.Paths.get("target/external-sscl-interop.json"), com.alibaba.fastjson2.JSON.toJSONString(sample).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        } finally {
            pool.shutdownNow();
            ReflectionTestUtils.setField(secrets, "secrets", originalSecrets);
            ReflectionTestUtils.setField(secrets, "activeId", originalId);
        }
    }
}
