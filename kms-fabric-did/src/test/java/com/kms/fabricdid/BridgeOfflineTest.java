package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

public class BridgeOfflineTest {
    private String oldUserDir, oldGmConfig;
    private Path runtime;
    private BridgeConfig config;
    private FakeDidSdk fake;
    private BindingService service;
    private final AtomicInteger initialized = new AtomicInteger();
    private BridgeServer server;
    @Before public void setup() throws Exception {
        oldUserDir = System.getProperty("user.dir");
        oldGmConfig = System.getProperty("fabricSDK.configuration");
        runtime = Files.createTempDirectory("fabric-did-offline-");
        Path work = Files.createDirectory(runtime.resolve("work"));
        System.setProperty("user.dir", work.toString());
        for (String name : new String[] {"connection.json", "certificate.pem", "msp-key.pem", "controller-public.pem", "gm.properties"})
            Files.write(runtime.resolve(name), "OFFLINE_TEST_FIXTURE_NOT_A_REAL_IDENTITY".getBytes(StandardCharsets.UTF_8));
        String props = "networkConfigPath=../connection.json\ncertificatePath=../certificate.pem\nprivateKeyPath=../msp-key.pem\nchannelName=offline\nmspId=offline\nchaincodeId=offline\nuserName=offline\nencryption=SM2\ntimeOut=10\n";
        Files.write(runtime.resolve("fabric.config.properties"), props.getBytes(StandardCharsets.UTF_8));
        Files.write(runtime.resolve("gm.properties"), ("org.hyperledger.fabric.sdk.crypto.default_crypto_suite_factory=org.hyperledger.fabric.sdk.security.GMCryptoSuiteFactory\n"
                + "org.hyperledger.fabric.sdk.hash_algorithm=SM3\norg.hyperledger.fabric.sdk.security_level=256\n").getBytes(StandardCharsets.UTF_8));
        System.setProperty("fabricSDK.configuration", runtime.resolve("gm.properties").toString());
        config = new BridgeConfig(environment());
        assertTrue(config.configured());
        fake = new FakeDidSdk();
        service = new BindingService(config, () -> { initialized.incrementAndGet(); return fake; });
    }
    @After public void cleanup() throws Exception {
        if (server != null) server.stop();
        System.setProperty("user.dir", oldUserDir);
        if (oldGmConfig == null) System.clearProperty("fabricSDK.configuration"); else System.setProperty("fabricSDK.configuration", oldGmConfig);
        try (java.util.stream.Stream<Path> files = Files.walk(runtime)) {
            files.sorted(java.util.Comparator.reverseOrder()).forEach(path -> { try { Files.delete(path); } catch (Exception ignored) { } });
        }
    }
    private Map<String, String> environment() {
        Map<String, String> env = new HashMap<>();
        env.put("FABRIC_DID_ENABLED", "true"); env.put("FABRIC_DID_WRITE_ENABLED", "true");
        env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "true"); env.put("FABRIC_DID_CHAIN_ID", "offline-test");
        env.put("FABRIC_DID_METHOD_ID", "offline"); env.put("INTERNAL_TOKEN", "offline-secret");
        env.put("FABRIC_DID_PROPERTIES_FILE", runtime.resolve("fabric.config.properties").toString());
        env.put("FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE", runtime.resolve("controller-public.pem").toString());
        env.put("FABRIC_DID_PORT", "0");
        return env;
    }
    private ObjectNode binding(String algorithm) {
        return Json.MAPPER.valueToTree(Json.map("schemaVersion", 1, "namespace", "kms-key-binding-v1", "eventId", "event-" + algorithm,
                "nodeId", "节点一", "algorithm", algorithm, "keyId", "logical-key-" + algorithm, "keyVersion", 2,
                "publicKey", "04aabbcc", "publicKeyHash", Json.digest("04aabbcc"), "status", "ACTIVE", "revision", 3,
                "eventType", "ROTATED", "recordedAt", "2026-10-09T10:15:00.123456"));
    }
    private ObjectNode prepare(String algorithm) { return Json.MAPPER.valueToTree(service.prepare(binding(algorithm))); }
    private ObjectNode verifyBody(ObjectNode prepared) {
        return Json.MAPPER.valueToTree(Json.map("did", prepared.get("did").asText(), "txId", prepared.get("txId").asText(),
                "metadataDigest", prepared.get("metadataDigest").asText(), "expectedMetadata", prepared.get("binding")));
    }
    @Test public void fourAlgorithmsCanonicalMetadataAndNoSubmitInPrepare() {
        for (String algorithm : new String[] {"SM2", "SSCL", "KYBER", "FALCON"}) {
            ObjectNode plan = prepare(algorithm);
            String metadata = plan.get("metadata").asText();
            assertTrue(metadata.startsWith("{\"algorithm\":"));
            assertTrue(metadata.contains("节点一"));
            assertFalse(metadata.contains("\\u"));
            assertEquals(Json.digest(metadata), plan.get("metadataDigest").asText());
            assertEquals(algorithm, plan.get("binding").get("algorithm").asText());
            assertTrue(plan.get("did").asText().contains(":kms-key-binding-v1:binding:"));
        }
        assertEquals(0, fake.submits); assertEquals(1, initialized.get());
    }
    @Test public void managementControllerKeyStableAcrossAlgorithmsAndRotations() {
        String controller = "-----BEGIN PUBLIC KEY-----\nOFFLINE_MANAGEMENT_PUBLIC_FIXTURE\n-----END PUBLIC KEY-----";
        for (String algorithm : new String[] {"SM2", "SSCL", "KYBER", "FALCON"}) {
            ObjectNode row = binding(algorithm);
            Binding first = new Binding(row, config);
            row.put("keyVersion", 3); row.put("publicKey", "04ddeeff"); row.put("publicKeyHash", Json.digest("04ddeeff"));
            Binding next = new Binding(row, config);
            com.yunphant.yunid.sdk.req.DocumentReq a = VendorDidSdk.documentRequest(first.did, first.json, controller);
            com.yunphant.yunid.sdk.req.DocumentReq b = VendorDidSdk.documentRequest(next.did, next.json, controller);
            assertEquals(controller, a.getPublicKey()); assertEquals(controller, b.getPublicKey());
            assertNotEquals(a.getPublicKey(), first.metadata.get("publicKey"));
            assertNotEquals(a.getId(), b.getId());
        }
        assertEquals(0, initialized.get());
    }
    @Test public void missingConfigurationNeverInitializesSdk() {
        Map<String, String> env = new HashMap<>(); env.put("FABRIC_DID_ENABLED", "true");
        BindingService missing = new BindingService(new BridgeConfig(env), () -> { throw new AssertionError("must not initialize"); });
        assertEquals("NOT_CONFIGURED", missing.status().get("status"));
        expect("NOT_CONFIGURED", () -> missing.prepare(binding("SM2")));
        assertEquals(0, initialized.get());
    }
    @Test public void disabledAndWriteDisabledAreIndependent() {
        Map<String, String> env = environment(); env.put("FABRIC_DID_ENABLED", "false");
        BindingService disabled = new BindingService(new BridgeConfig(env), () -> { throw new AssertionError("disabled SDK"); });
        assertEquals("DISABLED", disabled.status().get("status"));
        expect("DISABLED", () -> disabled.read("did:offline:example"));
        ObjectNode prepared = prepare("SM2");
        env = environment(); env.put("FABRIC_DID_WRITE_ENABLED", "false");
        BindingService readonly = new BindingService(new BridgeConfig(env), () -> fake);
        assertEquals("READY_READ_ONLY", readonly.status().get("status"));
        expect("WRITE_DISABLED", () -> readonly.submit(prepared));
        env = environment(); env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "false");
        BindingService unapproved = new BindingService(new BridgeConfig(env), () -> fake);
        expect("CHAIN_POLICY_NOT_APPROVED", () -> unapproved.submit(prepared));
    }
    @Test public void onlyTransactionValidAndExactMetadataConfirms() {
        ObjectNode plan = prepare("SM2");
        assertEquals("PENDING_VERIFICATION", service.submit(plan).get("status"));
        assertEquals("CONFIRMED", service.verify(verifyBody(plan)).get("status"));
        fake.valid = null;
        assertEquals("PENDING_VERIFICATION", service.verify(verifyBody(plan)).get("status"));
        fake.valid = false;
        assertEquals("FAILED", service.verify(verifyBody(plan)).get("status"));
        fake.valid = true; fake.document.put("metadata", "{}");
        assertEquals("FAILED", service.verify(verifyBody(plan)).get("status"));
    }
    @Test public void wrongReturnedDidAndDeactivatedCannotConfirm() {
        ObjectNode plan = prepare("KYBER"); service.submit(plan);
        fake.document.put("id", "did:offline:foreign");
        assertEquals("FAILED", service.verify(verifyBody(plan)).get("status"));
        fake.document.put("id", plan.get("did").asText()); fake.document.put("deactivated", true);
        assertEquals("FAILED", service.verify(verifyBody(plan)).get("status"));
    }
    @Test public void submittedPayloadIsNeverTransactionId() {
        ObjectNode plan = prepare("FALCON");
        Map<String, Object> submitted = service.submit(plan);
        assertEquals(plan.get("txId").asText(), submitted.get("txId"));
        assertNotEquals(submitted.get("txId"), submitted.get("sdkResult"));
        assertEquals("PENDING_VERIFICATION", submitted.get("status"));
    }
    @Test public void repeatedSubmitIdempotentAndConflictingDidRejected() {
        ObjectNode plan = prepare("SM2"); service.submit(plan);
        assertEquals("CONFIRMED", service.submit(plan).get("status")); assertEquals(1, fake.submits);
        fake.document.put("metadata", "foreign metadata");
        expect("DID_BINDING_CONFLICT", () -> service.submit(plan)); assertEquals(1, fake.submits);
    }
    @Test public void unknownAndPrivateFieldsAreRejected() {
        for (String forbidden : new String[] {"privateKey", "sm4Key", "deviceToken", "mspId", "arbitrary"}) {
            ObjectNode input = binding("SM2"); input.put(forbidden, "secret");
            expect("UNKNOWN_FIELD", () -> service.prepare(input));
        }
        ObjectNode input = binding("SM2"); input.put("publicKey", "-----BEGIN PRIVATE KEY-----");
        expect("INVALID_PUBLIC_KEY", () -> service.prepare(input));
        assertEquals(0, fake.submits);
    }
    @Test public void hashOfStoredTextAndCanonicalAlgorithmValidated() {
        ObjectNode input = binding("SM2"); input.put("publicKeyHash", Json.digest("different"));
        expect("PUBLIC_KEY_HASH_MISMATCH", () -> service.prepare(input));
        final ObjectNode unsupported = binding("SM2"); unsupported.put("algorithm", "ML-KEM");
        expect("INVALID_FIELD", () -> service.prepare(unsupported));
    }
    @Test public void invalidTxNonceAndPlanTamperingNeverSubmit() {
        ObjectNode plan = prepare("SM2"); plan.put("txId", "SDK_RETURNED_PAYLOAD_NOT_TXID");
        expect("INVALID_TX_ID", () -> service.submit(plan));
        final ObjectNode mismatch = prepare("SM2"); mismatch.put("nonce", FakeDidSdk.hex('c', 48));
        expect("TX_NONCE_MISMATCH", () -> service.submit(mismatch));
        final ObjectNode modified = prepare("SM2"); modified.put("metadata", "{}");
        expect("PREPARED_BINDING_MISMATCH", () -> service.submit(modified));
        assertEquals(0, fake.submits);
    }
    @Test public void verifyCannotTrustCallerDigestAlone() {
        ObjectNode plan = prepare("SM2"); service.submit(plan);
        ObjectNode verification = verifyBody(plan); verification.put("metadataDigest", "fake");
        expect("EXPECTED_BINDING_MISMATCH", () -> service.verify(verification));
    }
    @Test public void readPreservesLiteralDidAndMissingDeactivatedError() {
        fake.readError = "NOT_FOUND_OR_DEACTIVATED";
        expect("NOT_FOUND_OR_DEACTIVATED", () -> service.read("did:offline:literal:007"));
        assertEquals("did:offline:literal:007", fake.lastDid);
        fake.readError = "DID_READ_FAILED";
        expect("DID_READ_FAILED", () -> service.read("did:offline:literal:007"));
    }
    @Test public void knownInvalidOrCommittedTransactionNeverResubmitsWhenDidReadIsMissing() {
        ObjectNode plan = prepare("SM2");
        fake.submits = 1; fake.valid = false;
        assertEquals("FAILED", service.submit(plan).get("status")); assertEquals(1, fake.submits);
        fake.valid = true;
        assertEquals("PENDING_VERIFICATION", service.submit(plan).get("status")); assertEquals(1, fake.submits);
    }
    @Test public void timeoutReturnsPendingAndNoInventedReceipt() {
        ObjectNode plan = prepare("SM2"); fake.throwSubmit = true;
        Map<String, Object> response = service.submit(plan);
        assertEquals("PENDING_VERIFICATION", response.get("status"));
        assertEquals("SUBMISSION_OUTCOME_UNKNOWN", response.get("errorCode"));
        assertEquals(plan.get("txId").asText(), response.get("txId"));
    }
    @Test public void publicHealthAuthenticatedStatusNoConfigViaHttp() throws Exception {
        Map<String, String> env = new HashMap<>(); env.put("FABRIC_DID_ENABLED", "true"); env.put("FABRIC_DID_PORT", "0"); env.put("INTERNAL_TOKEN", "offline-secret");
        server = new BridgeServer(new BridgeConfig(env), () -> { throw new AssertionError("HTTP no-config must not initialize SDK"); }); server.start();
        assertEquals(200, http("/health", null, "GET", null).code);
        assertEquals(401, http("/internal/fabric-did/status", null, "GET", null).code);
        HttpReply status = http("/internal/fabric-did/status", "offline-secret", "GET", null);
        assertEquals(200, status.code); assertEquals("NOT_CONFIGURED", status.body.get("data").get("status").asText());
        assertEquals(503, http("/internal/fabric-did/bindings/prepare", "offline-secret", "POST", Json.encode(binding("SM2"))).code);
    }
    @Test public void fakeSdkFullHttpFlowIsExplicitlyOffline() throws Exception {
        server = new BridgeServer(config, () -> fake); server.start();
        HttpReply preparation = http("/internal/fabric-did/bindings/prepare", "offline-secret", "POST", Json.encode(binding("SSCL")));
        assertEquals(200, preparation.code); assertEquals(0, fake.submits);
        ObjectNode plan = (ObjectNode) preparation.body.get("data");
        HttpReply submission = http("/internal/fabric-did/bindings/submit", "offline-secret", "POST", Json.encode(plan));
        assertEquals("PENDING_VERIFICATION", submission.body.get("data").get("status").asText());
        HttpReply verified = http("/internal/fabric-did/bindings/verify", "offline-secret", "POST", Json.encode(verifyBody(plan)));
        assertEquals("CONFIRMED", verified.body.get("data").get("status").asText());
        HttpReply duplicateJson = http("/internal/fabric-did/bindings/prepare", "offline-secret", "POST", "{\"a\":1,\"a\":2}");
        assertEquals(400, duplicateJson.code);
    }
    private HttpReply http(String path, String token, String method, String request) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:" + server.port() + path).openConnection();
        connection.setRequestMethod(method); connection.setConnectTimeout(2000); connection.setReadTimeout(2000);
        if (token != null) connection.setRequestProperty("X-Internal-Token", token);
        if (request != null) {
            connection.setDoOutput(true); connection.setRequestProperty("Content-Type", "application/json");
            try (java.io.OutputStream out = connection.getOutputStream()) { out.write(request.getBytes(StandardCharsets.UTF_8)); }
        }
        int code = connection.getResponseCode();
        try (InputStream input = code >= 400 ? connection.getErrorStream() : connection.getInputStream(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) >= 0) bytes.write(buffer, 0, count);
            return new HttpReply(code, Json.MAPPER.readTree(bytes.toByteArray()));
        } finally { connection.disconnect(); }
    }
    private static void expect(String errorCode, Runnable action) {
        try { action.run(); fail("expected " + errorCode); } catch (BridgeException e) { assertEquals(errorCode, e.errorCode); }
    }
    private static class HttpReply {
        final int code; final JsonNode body;
        HttpReply(int code, JsonNode body) { this.code = code; this.body = body; }
    }
    // 假 SDK 只存在于测试源码，生产不存在自动 CONFIRMED 的模拟开关。
    private static class FakeDidSdk implements DidSdk {
        final String txId = hex('a', 64), nonce = hex('b', 48);
        int submits; Boolean valid = true; boolean throwSubmit; String lastDid, readError;
        Map<String, Object> document;
        static String hex(char value, int size) { StringBuilder text = new StringBuilder(); for (int i = 0; i < size; i++) text.append(value); return text.toString(); }
        @Override public Map<String, Object> newTransaction() { return Json.map("txId", txId, "nonce", nonce); }
        @Override public String transactionId(String candidate) { return nonce.equals(candidate) ? txId : hex('d', 64); }
        @Override public Map<String, Object> read(String did) {
            lastDid = did;
            if (readError != null) throw new BridgeException(502, readError);
            if (document == null) throw new BridgeException(404, "NOT_FOUND");
            return document;
        }
        @Override public String create(String did, String metadata, String nonce) {
            submits++;
            if (throwSubmit) throw new IllegalStateException("offline timeout");
            document = Json.map("id", did, "metadata", metadata, "deactivated", false, "status", "FOUND");
            return "SDK_PAYLOAD_OR_DID_NOT_A_TRANSACTION_ID";
        }
        @Override public Boolean transactionValid(String txId) { return submits == 0 ? null : valid; }
    }
}
