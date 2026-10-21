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
        String props = "networkConfigPath=../connection.json\ncertificatePath=../certificate.pem\nprivateKeyPath=../msp-key.pem\nchannelName=offline\nmethodId=offline\nmspId=offline\nchaincodeId=offline\nuserName=offline\nencryption=SM2\ntimeOut=10\n";
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
        env.put("KMS_CHAIN_WRITES_ENABLED", "true");
        env.put("FABRIC_DID_ENABLED", "true"); env.put("FABRIC_DID_WRITE_ENABLED", "true");
        env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "true"); env.put("FABRIC_DID_CHAIN_ID", "offline-test");
        env.put("FABRIC_DID_METHOD_ID", "offline"); env.put("INTERNAL_TOKEN", "offline-secret");
        env.put("FABRIC_DID_PROPERTIES_FILE", runtime.resolve("fabric.config.properties").toString());
        env.put("FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE", runtime.resolve("controller-public.pem").toString());
        env.put("FABRIC_DID_PORT", "0");
        env.put("FABRIC_DID_SYSPID_RECORDS_DIR", runtime.resolve("sys-pids").toString());
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
        Map<String, String> env = new HashMap<>(); env.put("FABRIC_DID_ENABLED", "true"); env.put("KMS_CHAIN_WRITES_ENABLED", "true");
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
        assertEquals("PREPARED", readonly.prepare(binding("SM2")).get("status"));
        expect("WRITE_DISABLED", () -> readonly.submit(prepared));
        env = environment(); env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "false");
        BindingService unapproved = new BindingService(new BridgeConfig(env), () -> fake);
        expect("CHAIN_POLICY_NOT_APPROVED", () -> unapproved.submit(prepared));
    }
    @Test public void globalPauseMissingFalseAndInvalidNeverInvokeSdk() {
        for (String value : new String[] {null, "false", "", "yes", "1", " true ", "invalid"}) {
            Map<String, String> env = environment();
            if (value == null) env.remove("KMS_CHAIN_WRITES_ENABLED"); else env.put("KMS_CHAIN_WRITES_ENABLED", value);
            BindingService paused = new BindingService(new BridgeConfig(env), () -> { throw new AssertionError("paused SDK factory"); });
            assertEquals("PAUSED", paused.status().get("chainWriteState"));
            assertEquals(false, paused.status().get("writeEnabled"));
            assertEquals("READY_READ_ONLY", paused.status().get("status"));
            expect("CHAIN_WRITES_PAUSED", () -> paused.prepare(binding("SM2")));
            expect("CHAIN_WRITES_PAUSED", () -> paused.submit(Json.MAPPER.createObjectNode()));
        }
        assertEquals(0, initialized.get()); assertEquals(0, fake.calls); assertEquals(0, fake.submits);
    }
    @Test public void handoffPrepareWorksWhileWritesPausedAndNeverSubmits() {
        Map<String, String> env = environment(); env.put("KMS_CHAIN_WRITES_ENABLED", "false");
        BindingService paused = new BindingService(new BridgeConfig(env), () -> fake);
        Map<String, Object> handoff = paused.prepareHandoff(binding("SM2"));
        assertEquals("PREPARED", handoff.get("status"));
        assertEquals(false, handoff.get("submitted"));
        assertNotNull(handoff.get("txId")); assertNotNull(handoff.get("nonce"));
        assertEquals(0, fake.submits);
    }
    @Test public void globalPausePrecedesMissingConfigurationAndDisabledBridge() {
        for (String enabled : new String[] {"true", "false"}) {
            Map<String, String> env = new HashMap<>();
            env.put("FABRIC_DID_ENABLED", enabled); env.put("FABRIC_DID_WRITE_ENABLED", "true");
            env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "true");
            BindingService paused = new BindingService(new BridgeConfig(env), () -> { throw new AssertionError("missing paused SDK factory"); });
            assertFalse(paused.config.configured());
            expect("CHAIN_WRITES_PAUSED", () -> paused.prepare(null));
            expect("CHAIN_WRITES_PAUSED", () -> paused.submit(null));
            expect("true".equals(enabled) ? "NOT_CONFIGURED" : "DISABLED", () -> paused.read("did:offline:history"));
        }
        assertEquals(0, initialized.get()); assertEquals(0, fake.calls);
    }
    @Test public void pausedCachedSdkKeepsHistoricalReadAndVerifyWithoutPrepareOrSubmit() {
        ObjectNode plan = prepare("KYBER"); service.submit(plan);
        Map<String, String> env = environment(); env.put("KMS_CHAIN_WRITES_ENABLED", "false");
        AtomicInteger cachedFactoryCalls = new AtomicInteger();
        BindingService paused = new BindingService(new BridgeConfig(env), () -> { cachedFactoryCalls.incrementAndGet(); return fake; });
        assertEquals(plan.get("did").asText(), paused.read(plan.get("did").asText()).get("did"));
        Map<String, Object> verified = paused.verify(verifyBody(plan));
        assertEquals("CONFIRMED", verified.get("status"));
        assertEquals(true, verified.get("transactionValid")); assertEquals(true, verified.get("metadataMatches"));
        int before = fake.calls;
        expect("CHAIN_WRITES_PAUSED", () -> paused.prepare(binding("KYBER")));
        expect("CHAIN_WRITES_PAUSED", () -> paused.submit(plan));
        assertEquals(before, fake.calls); assertEquals(1, cachedFactoryCalls.get()); assertEquals(1, fake.submits);
        assertEquals("CONFIRMED", verified.get("status"));
    }
    @Test public void globalTruePreservesLocalWriteAndPolicyGates() {
        Map<String, String> env = environment(); env.put("KMS_CHAIN_WRITES_ENABLED", "TRUE");
        BridgeConfig allowed = new BridgeConfig(env);
        assertEquals("ENABLED", allowed.chainWriteState()); assertTrue(allowed.effectiveWriteEnabled());
        env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "false");
        BindingService unapproved = new BindingService(new BridgeConfig(env), () -> fake);
        assertEquals("PREPARED", unapproved.prepare(binding("SM2")).get("status"));
        expect("CHAIN_POLICY_NOT_APPROVED", () -> unapproved.submit(Json.MAPPER.createObjectNode()));
        assertEquals(false, unapproved.status().get("writeEnabled")); assertEquals(0, fake.submits);
    }
    @Test public void pausedHealthStatusAndWriteErrorsViaHttpNeverInitializeSdk() throws Exception {
        Map<String, String> env = environment(); env.remove("KMS_CHAIN_WRITES_ENABLED"); env.remove("FABRIC_DID_METHOD_ID");
        server = new BridgeServer(new BridgeConfig(env), () -> { throw new AssertionError("HTTP paused SDK factory"); }); server.start();
        HttpReply health = http("/health", null, "GET", null);
        assertEquals(200, health.code); assertEquals("PAUSED", health.body.get("data").get("chainWriteState").asText());
        assertFalse(health.body.get("data").get("writeEnabled").asBoolean());
        assertEquals(401, http("/internal/fabric-did/bindings/prepare", null, "POST", "{}").code);
        HttpReply status = http("/internal/fabric-did/status", "offline-secret", "GET", null);
        assertEquals("PAUSED", status.body.get("data").get("chainWriteState").asText());
        assertFalse(status.body.get("data").get("writeEnabled").asBoolean());
        assertEquals("NOT_CONFIGURED", status.body.get("data").get("status").asText());
        for (String action : new String[] {"prepare", "submit"}) {
            HttpReply reply = http("/internal/fabric-did/bindings/" + action, "offline-secret", "POST", "{}");
            assertEquals(503, reply.code); assertEquals("CHAIN_WRITES_PAUSED", reply.body.get("data").get("errorCode").asText());
        }
        assertEquals(0, initialized.get()); assertEquals(0, fake.calls); assertEquals(0, fake.submits);
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
        Map<String, String> env = new HashMap<>(); env.put("FABRIC_DID_ENABLED", "true"); env.put("FABRIC_DID_PORT", "0"); env.put("INTERNAL_TOKEN", "offline-secret"); env.put("KMS_CHAIN_WRITES_ENABLED", "true");
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
    private static final String SYS_PID = "3059301306072a8648ce3d020106082a811ccf5501822d034200044a02994903204dccb1bf325586fc028dcbe556fad25b6101abb307ce47d2baeceaa2c62fb3ee36ca3491137d6f2586cdc9ef4c88b2caa6149691daebdfc14db1";
    private ObjectNode systemBody() { return Json.MAPPER.valueToTree(Json.map("sysPid", SYS_PID)); }
    private SysPidService systemService() { return new SysPidService(config, () -> { initialized.incrementAndGet(); return fake; }); }
    private Path systemRecordFolder() { return config.sysPidRecordsPath.resolve(Json.digest(config.chainId + "\n" + SysPidService.did(SYS_PID, config))); }
    @Test public void generatedSysPidIsDistinctAndSurvivesRetryAndServiceRestart() {
        fake.generateRealPublicKeys = true;
        JsonNode firstRequest = Json.MAPPER.valueToTree(Json.map("requestId", "00000000-0000-4000-8000-000000000001"));
        Map<String, Object> first = systemService().prepare(firstRequest);
        Map<String, Object> duplicate = systemService().prepare(firstRequest);
        assertEquals(first, duplicate); assertEquals(1, fake.systemKeys); assertEquals(0, fake.submits);
        assertEquals("PREPARED", first.get("status")); assertEquals(false, first.get("submitted"));
        Map<String, Object> second = systemService().prepare(Json.MAPPER.valueToTree(
                Json.map("requestId", "00000000-0000-4000-8000-000000000002")));
        assertNotEquals(first.get("sysPid"), second.get("sysPid"));
        assertFalse(Json.encode(first).contains("PRIVATE KEY")); assertFalse(first.containsKey("nonce"));
        assertEquals("did:offline:offline:zhxun-test" + first.get("sysPid"), first.get("did"));
    }
    @Test public void generatedSysPidCanBeSubmittedAndQueriedWithoutCreatingAnotherIdentity() {
        fake.generateRealPublicKeys = true;
        Map<String, Object> prepared = systemService().prepare(Json.MAPPER.valueToTree(
                Json.map("requestId", "00000000-0000-4000-8000-000000000003")));
        JsonNode input = Json.MAPPER.valueToTree(Json.map("sysPid", prepared.get("sysPid")));
        Map<String, Object> submitted = systemService().onchain(input);
        assertEquals("CONFIRMED", submitted.get("status")); assertEquals(prepared.get("txId"), submitted.get("txId"));
        assertEquals(1, fake.systemKeys); assertEquals(1, fake.submits);
        assertEquals("CONFIRMED", systemService().verify(input).get("status"));
        assertEquals("CONFIRMED", systemService().onchain(input).get("status"));
        assertEquals(1, fake.submits);
    }
    @Test public void generatedSysPidRejectsReadOnlyModeAndInvalidIdBeforeAllocatingKeys() {
        expect("INVALID_REQUEST_ID", () -> systemService().prepare(Json.MAPPER.valueToTree(Json.map("requestId", "../record"))));
        expect("UNKNOWN_FIELD", () -> systemService().prepare(Json.MAPPER.valueToTree(Json.map("requestId", "x", "privateKey", "secret"))));
        Map<String, String> env = environment(); env.put("FABRIC_DID_WRITE_ENABLED", "false");
        SysPidService readonly = new SysPidService(new BridgeConfig(env), () -> fake);
        expect("WRITE_DISABLED", () -> readonly.prepare(Json.MAPPER.valueToTree(Json.map("requestId", "00000000-0000-4000-8000-000000000001"))));
        assertEquals(0, fake.systemKeys);
    }
    @Test public void systemIdentifierRequestMatchesVendorSpecification() {
        String did = SysPidService.did(SYS_PID, config);
        assertEquals("did:offline:offline:zhxun-test" + SYS_PID, did);
        com.yunphant.yunid.sdk.req.DocumentReq request = VendorDidSdk.systemIdentifierRequest(did, SYS_PID, "GENERATED_CONTROLLER_PUBLIC_KEY");
        assertEquals(did, request.getId()); assertEquals(SYS_PID, request.getMetadata());
        assertEquals("ZHXUN_DID", request.getAlsoKnownAs()); assertEquals("GENERATED_CONTROLLER_PUBLIC_KEY", request.getPublicKey());
        assertEquals(0, initialized.get());
    }
    @Test public void vendorMissingDidAcceptsOnlyKnownNumericOrDelimitedSdkCode() {
        assertTrue(VendorDidSdk.isMissingDidError(new com.yunphant.yunid.sdk.exception.DidSdkException(400001, "not found")));
        assertTrue(VendorDidSdk.isMissingDidError(new com.yunphant.yunid.sdk.exception.DidSdkException("400001|DID不存在")));
        assertFalse(VendorDidSdk.isMissingDidError(new com.yunphant.yunid.sdk.exception.DidSdkException(900000, "blockchain error")));
        assertFalse(VendorDidSdk.isMissingDidError(new com.yunphant.yunid.sdk.exception.DidSdkException("network error mentions 400001")));
        assertFalse(VendorDidSdk.isMissingDidError(new com.yunphant.yunid.sdk.exception.DidSdkException("4000019|different code")));
    }
    @Test public void systemOnchainPersistsPlanBeforeSdkAndKeepsPrivateKeyLocal() throws Exception {
        fake.beforeSystemSubmit = () -> {
            try {
                JsonNode saved = Json.MAPPER.readTree(Files.readAllBytes(systemRecordFolder().resolve("record.json")));
                assertEquals("PENDING_VERIFICATION", saved.get("status").asText());
                assertEquals(SYS_PID, saved.get("metadata").asText());
                assertTrue(Files.isRegularFile(systemRecordFolder().resolve("controller-private.pem")));
                assertFalse(saved.has("privateKey"));
            } catch (Exception e) { throw new AssertionError(e); }
        };
        Map<String, Object> result = systemService().onchain(systemBody());
        assertEquals("CONFIRMED", result.get("status")); assertEquals(fake.txId, result.get("txId"));
        assertEquals(SYS_PID, fake.document.get("metadata")); assertEquals("ZHXUN_DID", fake.document.get("alsoKnownAs"));
        assertFalse(Json.encode(result).contains("PRIVATE KEY")); assertFalse(result.containsKey("nonce"));
        assertTrue(Files.isRegularFile(systemRecordFolder().resolve("verification.json")));
        assertEquals(1, fake.submits); assertEquals(1, fake.systemKeys);
    }
    @Test public void systemRetryAndRestartReuseRecordedTransactionAndKey() {
        SysPidService service = systemService();
        Map<String, Object> first = service.onchain(systemBody());
        assertEquals("CONFIRMED", service.onchain(systemBody()).get("status"));
        assertEquals(first.get("txId"), systemService().onchain(systemBody()).get("txId"));
        assertEquals(1, fake.submits); assertEquals(1, fake.systemKeys);
    }
    @Test public void systemTimeoutAndRestartNeverResubmitUnknownOutcome() {
        fake.throwSubmit = true;
        Map<String, Object> result = systemService().onchain(systemBody());
        assertEquals("PENDING_VERIFICATION", result.get("status"));
        assertEquals("SUBMISSION_OUTCOME_UNKNOWN", result.get("errorCode"));
        assertEquals("PENDING_VERIFICATION", systemService().onchain(systemBody()).get("status"));
        assertEquals(1, fake.submits); assertEquals(1, fake.systemKeys);
    }
    @Test public void explicitSystemRetryRequiresConfirmedAbsenceAndReusesKeyAndTransaction() {
        fake.throwSubmit = true; fake.valid = null;
        systemService().onchain(systemBody());
        assertEquals(1, fake.submits);
        systemService().retryUnrecordedTransaction(systemBody());
        assertEquals(1, fake.submits); // 普通未知结果或网络失败，不能当作账本已明确不存在。
        fake.absent = true; fake.throwSubmit = false;
        Map<String, Object> retried = systemService().retryUnrecordedTransaction(systemBody());
        assertEquals(fake.txId, retried.get("txId")); assertEquals(2, fake.submits); assertEquals(1, fake.systemKeys);
        fake.valid = true;
        assertEquals("CONFIRMED", systemService().verify(systemBody()).get("status"));
        systemService().retryUnrecordedTransaction(systemBody()); assertEquals(2, fake.submits);
    }
    @Test public void systemVerificationRequiresValidTransactionAndExactDocument() {
        SysPidService service = systemService(); service.onchain(systemBody());
        fake.valid = null; assertEquals("PENDING_VERIFICATION", service.verify(systemBody()).get("status"));
        fake.valid = false; assertEquals("FAILED", service.verify(systemBody()).get("status"));
        fake.valid = true; fake.document.put("metadata", "foreign");
        assertEquals("FAILED", service.verify(systemBody()).get("status"));
        fake.document.put("metadata", SYS_PID); fake.document.put("alsoKnownAs", "other");
        assertEquals("FAILED", service.verify(systemBody()).get("status"));
        fake.document.put("alsoKnownAs", "ZHXUN_DID"); fake.document.put("verificationMethod", java.util.Collections.emptyList());
        assertEquals("FAILED", service.verify(systemBody()).get("status"));
        fake.document.put("deactivated", true);
        assertEquals("FAILED", service.verify(systemBody()).get("status"));
        assertEquals(1, fake.submits);
    }
    @Test public void migratedCreatorSerializationCanVerifyWithoutResubmitting() {
        systemService().onchain(systemBody()); fake.migratedCreator = true;
        assertEquals("CONFIRMED", systemService().verify(systemBody()).get("status"));
        assertEquals("CONFIRMED", systemService().onchain(systemBody()).get("status"));
        assertEquals(1, fake.submits); assertEquals(1, fake.systemKeys);
    }
    @Test public void migratedCreatorCannotRetryWithAnotherTransactionId() throws Exception {
        fake.throwSubmit = true; fake.valid = null;
        systemService().onchain(systemBody()); fake.migratedCreator = true; fake.absent = true;
        byte[] original = Files.readAllBytes(systemRecordFolder().resolve("record.json"));
        expect("SYSPID_SIGNER_SERIALIZATION_CHANGED", () -> systemService().retryUnrecordedTransaction(systemBody()));
        assertArrayEquals(original, Files.readAllBytes(systemRecordFolder().resolve("record.json")));
        assertEquals(1, fake.submits); assertEquals(1, fake.systemKeys);
    }
    @Test public void existingSystemDocumentIsNotOverwrittenOrGivenInventedReceipt() {
        fake.document = Json.map("id", SysPidService.did(SYS_PID, config), "metadata", SYS_PID, "alsoKnownAs", "ZHXUN_DID", "deactivated", false);
        Map<String, Object> result = systemService().onchain(systemBody());
        assertEquals("EXISTS", result.get("status")); assertFalse(result.containsKey("txId"));
        assertEquals(0, fake.submits); assertEquals(0, fake.systemKeys);
        fake.document.put("metadata", "foreign");
        expect("SYSPID_DOCUMENT_CONFLICT", () -> systemService().onchain(systemBody()));
        assertEquals(0, fake.submits);
    }
    @Test public void systemPidMustBeDerSequenceNotBusinessKeyIdOrPem() {
        for (String invalid : new String[] {"logical-key-SM2", "-----BEGIN PUBLIC KEY-----", "0x" + SYS_PID,
                " " + SYS_PID, "abc", "020101", SYS_PID + "00", "308103020101", ""}) {
            ObjectNode body = systemBody(); body.put("sysPid", invalid);
            expect(invalid.isEmpty() ? "INVALID_FIELD" : "INVALID_SYS_PID", () -> systemService().onchain(body));
        }
        ObjectNode injected = systemBody(); injected.put("privateKey", "never accept");
        expect("UNKNOWN_FIELD", () -> systemService().onchain(injected));
        assertEquals(0, initialized.get()); assertEquals(0, fake.systemKeys);
    }
    @Test public void systemMethodMustBeExplicitAlphabeticAndMatchSdkConfiguration() {
        config.fabric.remove("methodId");
        expect("SYSPID_METHOD_ID_NOT_CONFIGURED", () -> systemService().onchain(systemBody()));
        config.fabric.setProperty("methodId", "method1");
        expect("SYSPID_METHOD_ID_NOT_CONFIGURED", () -> systemService().onchain(systemBody()));
        config.fabric.setProperty("methodId", "another");
        expect("SYSPID_METHOD_ID_MISMATCH", () -> systemService().onchain(systemBody()));
        assertEquals(0, initialized.get());
    }
    @Test public void systemWriteGatesPrecedeAllSdkCallsButVerificationWorksWhenPaused() {
        systemService().onchain(systemBody());
        Map<String, String> env = environment(); env.put("KMS_CHAIN_WRITES_ENABLED", "false");
        SysPidService paused = new SysPidService(new BridgeConfig(env), () -> fake);
        int before = fake.calls;
        expect("CHAIN_WRITES_PAUSED", () -> paused.onchain(systemBody()));
        assertEquals(before, fake.calls); assertEquals("CONFIRMED", paused.verify(systemBody()).get("status"));
        env = environment(); env.put("FABRIC_DID_WRITE_ENABLED", "false");
        SysPidService disabled = new SysPidService(new BridgeConfig(env), () -> { throw new AssertionError("No SDK"); });
        expect("WRITE_DISABLED", () -> disabled.onchain(systemBody()));
        env = environment(); env.put("FABRIC_DID_CREATE_POLICY_APPROVED", "false");
        SysPidService unapproved = new SysPidService(new BridgeConfig(env), () -> { throw new AssertionError("No SDK"); });
        expect("CHAIN_POLICY_NOT_APPROVED", () -> unapproved.onchain(systemBody()));
    }
    @Test public void systemStorageIsMandatoryAndFailureCannotSubmit() throws Exception {
        Map<String, String> env = environment(); env.remove("FABRIC_DID_SYSPID_RECORDS_DIR");
        SysPidService noStorage = new SysPidService(new BridgeConfig(env), () -> { throw new AssertionError("No SDK"); });
        expect("SYSPID_RECORDS_NOT_CONFIGURED", () -> noStorage.onchain(systemBody()));
        Path file = runtime.resolve("not-a-folder"); Files.write(file, new byte[] {1});
        env = environment(); env.put("FABRIC_DID_SYSPID_RECORDS_DIR", file.toString());
        SysPidService badStorage = new SysPidService(new BridgeConfig(env), () -> { throw new AssertionError("No SDK"); });
        expect("SYSPID_RECORD_STORAGE_FAILED", () -> badStorage.onchain(systemBody()));
        expect("SYSPID_RECORD_NOT_FOUND", () -> systemService().verify(systemBody()));
        assertEquals(0, fake.submits);
    }
    @Test public void systemTamperedTransactionRecordCannotSubmitAgain() throws Exception {
        systemService().onchain(systemBody());
        Path record = systemRecordFolder().resolve("record.json");
        ObjectNode plan = (ObjectNode) Json.MAPPER.readTree(Files.readAllBytes(record));
        plan.put("nonce", FakeDidSdk.hex('c', 48));
        Files.write(record, Json.encode(plan).getBytes(StandardCharsets.UTF_8));
        expect("SYSPID_RECORD_MISMATCH", () -> systemService().onchain(systemBody()));
        assertEquals(1, fake.submits);
    }
    @Test public void systemHttpRequiresAuthenticationAndAcceptsOnlySysPid() throws Exception {
        server = new BridgeServer(config, () -> fake); server.start();
        String path = "/internal/fabric-did/sys-pids/onchain";
        assertEquals(401, http(path, null, "POST", Json.encode(systemBody())).code);
        assertEquals(400, http(path, "offline-secret", "POST", "{\"sysPid\":42}").code);
        ObjectNode extra = systemBody(); extra.put("publicKey", "not allowed");
        assertEquals(400, http(path, "offline-secret", "POST", Json.encode(extra)).code);
        assertEquals(0, fake.submits);
        HttpReply result = http(path, "offline-secret", "POST", Json.encode(systemBody()));
        assertEquals(200, result.code); assertEquals("CONFIRMED", result.body.get("data").get("status").asText());
        HttpReply verified = http("/internal/fabric-did/sys-pids/verify", "offline-secret", "POST", Json.encode(systemBody()));
        assertEquals("CONFIRMED", verified.body.get("data").get("status").asText()); assertEquals(1, fake.submits);
    }
    @Test public void vendorGeneratesRealIndependentSm2SystemKeysOffline() {
        Map<String, String> first = VendorDidSdk.generateSystemKey(), second = VendorDidSdk.generateSystemKey();
        assertTrue(first.get("publicKey").contains("BEGIN PUBLIC KEY"));
        assertTrue(first.get("privateKey").contains("PRIVATE KEY"));
        assertNotEquals(first.get("publicKey"), second.get("publicKey"));
        com.yunphant.core.service.KmsService kms = new com.yunphant.core.service.impl.KmsServiceImpl();
        String signature = kms.sign(first.get("privateKey"), "offline-system-identifier-test");
        assertTrue(kms.verify(first.get("publicKey"), "offline-system-identifier-test", signature));
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
        int submits, calls, systemKeys; Boolean valid = true; boolean throwSubmit, absent, migratedCreator; String lastDid, readError;
        Runnable beforeSystemSubmit;
        boolean generateRealPublicKeys;
        Map<String, Object> document;
        static String hex(char value, int size) { StringBuilder text = new StringBuilder(); for (int i = 0; i < size; i++) text.append(value); return text.toString(); }
        @Override public Map<String, Object> newTransaction() { calls++; return Json.map("txId", txId, "nonce", nonce); }
        @Override public String transactionId(String candidate) { calls++; return nonce.equals(candidate) && !migratedCreator ? txId : hex('d', 64); }
        @Override public boolean matchesRecordedTransactionId(String candidate, String expected) {
            return migratedCreator && nonce.equals(candidate) && txId.equals(expected) || DidSdk.super.matchesRecordedTransactionId(candidate, expected);
        }
        @Override public Map<String, Object> read(String did) {
            calls++; lastDid = did;
            if (readError != null) throw new BridgeException(502, readError);
            if (document == null) throw new BridgeException(404, "NOT_FOUND");
            return document;
        }
        @Override public String create(String did, String metadata, String nonce) {
            calls++; submits++;
            if (throwSubmit) throw new IllegalStateException("offline timeout");
            document = Json.map("id", did, "metadata", metadata, "deactivated", false, "status", "FOUND");
            return "SDK_PAYLOAD_OR_DID_NOT_A_TRANSACTION_ID";
        }
        @Override public Map<String, String> newSystemKey() {
            systemKeys++;
            if (generateRealPublicKeys) return VendorDidSdk.generateSystemKey();
            Map<String, String> result = new HashMap<>();
            result.put("publicKey", "-----BEGIN PUBLIC KEY-----\nOFFLINE\n-----END PUBLIC KEY-----");
            result.put("privateKey", "-----BEGIN PRIVATE KEY-----\nOFFLINE\n-----END PRIVATE KEY-----");
            return result;
        }
        @Override public String createSystemIdentifier(String did, String sysPid, String publicKey, String nonce) {
            if (beforeSystemSubmit != null) beforeSystemSubmit.run();
            String result = create(did, sysPid, nonce);
            document.put("alsoKnownAs", "ZHXUN_DID");
            document.put("verificationMethod", java.util.Collections.singletonList(Json.map("publicKeyPem", publicKey)));
            return result;
        }
        @Override public Boolean transactionValid(String txId) { calls++; return submits == 0 ? null : valid; }
        @Override public boolean transactionAbsent(String txId) { calls++; return absent; }
    }
}
