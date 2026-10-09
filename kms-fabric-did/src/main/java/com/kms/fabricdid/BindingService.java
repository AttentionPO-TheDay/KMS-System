package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;

final class BindingService {
    final BridgeConfig config;
    private final DidSdk.Factory factory;
    private volatile DidSdk instance;
    BindingService(BridgeConfig config, DidSdk.Factory factory) { this.config = config; this.factory = factory; }
    private DidSdk sdk() {
        config.requireRead();
        if (instance == null) synchronized (this) { if (instance == null) instance = factory.create(); }
        return instance;
    }
    Map<String, Object> status() {
        return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "enabled", config.enabled,
                "configured", config.configured(), "writeEnabled", config.effectiveWriteEnabled(),
                "chainWriteState", config.chainWriteState(),
                "status", config.status(), "missingFields", config.missingFields,
                "capabilities", Json.map("immutableBinding", true, "transactionVerification", true,
                "currentNodeProjection", false, "compareAndSet", false, "lifecycleEquivalent", false,
                "networkChecked", false, "createPolicyApproved", config.policyApproved));
    }
    Map<String, Object> read(String did) {
        if (did == null || !did.startsWith("did:") || did.length() > 512) throw new BridgeException(400, "INVALID_DID");
        Map<String, Object> response = sdk().read(did);
        if (!did.equals(response.get("id"))) throw new BridgeException(502, "DID_MISMATCH");
        return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", did, "document", response, "status", response.get("status"));
    }
    Map<String, Object> prepare(JsonNode body) {
        config.requireChainWrites();
        config.requireRead();
        Binding binding = new Binding(body, config);
        Map<String, Object> transaction = sdk().newTransaction();
        String txId = String.valueOf(transaction.get("txId")), nonce = String.valueOf(transaction.get("nonce"));
        validateTransaction(txId, nonce);
        if (!txId.equals(sdk().transactionId(nonce))) throw new BridgeException(502, "TX_NONCE_MISMATCH");
        // prepare 不提交；调用方必须先在 durable outbox 保存这两个字段，再允许 submit。
        return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", binding.did,
                "txId", txId, "nonce", nonce, "metadata", binding.json, "metadataDigest", binding.digest,
                "binding", binding.metadata, "prepared", true, "status", "PREPARED",
                "latestProjection", Json.map("status", "UNSUPPORTED"));
    }
    synchronized Map<String, Object> submit(JsonNode body) {
        config.requireWrite();
        Binding.fields(body, new HashSet<>(Arrays.asList("provider", "chainId", "did", "txId", "nonce", "metadata", "metadataDigest", "binding", "prepared", "status", "latestProjection")));
        Binding binding = new Binding(body.get("binding"), config);
        String txId = Json.text(body, "txId"), nonce = Json.text(body, "nonce");
        validateTransaction(txId, nonce);
        if (!binding.did.equals(Json.text(body, "did")) || !binding.digest.equals(Json.text(body, "metadataDigest"))
                || !binding.json.equals(Json.text(body, "metadata")) || !config.chainId.equals(Json.text(body, "chainId"))
                || !"FABRIC_DID".equals(Json.text(body, "provider"))) throw new BridgeException(409, "PREPARED_BINDING_MISMATCH");
        DidSdk sdk = sdk();
        if (!txId.equals(sdk.transactionId(nonce))) throw new BridgeException(409, "TX_NONCE_MISMATCH");
        Map<String, Object> existing = null;
        try { existing = sdk.read(binding.did); }
        catch (BridgeException e) {
            if (!"NOT_FOUND".equals(e.errorCode) && !"NOT_FOUND_OR_DEACTIVATED".equals(e.errorCode)) throw e;
        }
        if (existing != null) {
            if (!matches(existing, binding.did, binding.json)) throw new BridgeException(409, "DID_BINDING_CONFLICT");
            return verification(binding.did, txId, binding.json, binding.digest, sdk);
        }
        // 已知交易（包括无效交易）只能核对，不能在回读暂缺时重发同一 nonce。
        if (sdk.transactionValid(txId) != null) return verification(binding.did, txId, binding.json, binding.digest, sdk);
        // 超时属于待核对：不能重新生成 nonce，更不能将返回字符串当交易回执。
        try {
            String result = sdk.create(binding.did, binding.json, nonce);
            return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", binding.did,
                    "txId", txId, "metadataDigest", binding.digest, "status", "PENDING_VERIFICATION", "sdkResult", result);
        } catch (Exception e) {
            return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", binding.did,
                    "txId", txId, "metadataDigest", binding.digest, "status", "PENDING_VERIFICATION", "errorCode", "SUBMISSION_OUTCOME_UNKNOWN");
        }
    }
    Map<String, Object> verify(JsonNode body) {
        Binding.fields(body, new HashSet<>(Arrays.asList("provider", "chainId", "did", "txId", "metadataDigest", "expectedMetadata", "binding", "nonce")));
        String did = Json.text(body, "did"), txId = Json.text(body, "txId"), digest = Json.text(body, "metadataDigest");
        if (!txId.matches("[0-9a-f]{64}")) throw new BridgeException(400, "INVALID_TX_ID");
        JsonNode expected = body.get("expectedMetadata");
        if (expected == null) throw new BridgeException(400, "MISSING_EXPECTED_METADATA");
        if (expected.isTextual()) {
            try { expected = Json.MAPPER.readTree(expected.asText()); }
            catch (Exception e) { throw new BridgeException(400, "INVALID_EXPECTED_METADATA"); }
        }
        Binding binding = new Binding(expected, config);
        if (!binding.did.equals(did) || !binding.digest.equals(digest)) throw new BridgeException(409, "EXPECTED_BINDING_MISMATCH");
        if (body.has("provider") && !"FABRIC_DID".equals(Json.text(body, "provider"))) throw new BridgeException(409, "PROVIDER_MISMATCH");
        if (body.has("chainId") && !config.chainId.equals(Json.text(body, "chainId"))) throw new BridgeException(409, "CHAIN_MISMATCH");
        return verification(did, txId, binding.json, digest, sdk());
    }
    private Map<String, Object> verification(String did, String txId, String metadata, String digest, DidSdk sdk) {
        Boolean valid = sdk.transactionValid(txId);
        Boolean matches = null;
        String errorCode = null;
        try { matches = matches(sdk.read(did), did, metadata); }
        catch (BridgeException e) { errorCode = e.errorCode; }
        catch (Exception e) { errorCode = "DID_READ_FAILED"; }
        String status = "PENDING_VERIFICATION";
        if (Boolean.FALSE.equals(valid)) { status = "FAILED"; errorCode = "TRANSACTION_INVALID"; }
        else if (Boolean.FALSE.equals(matches)) { status = "FAILED"; errorCode = "METADATA_MISMATCH"; }
        else if (Boolean.TRUE.equals(valid) && Boolean.TRUE.equals(matches)) status = "CONFIRMED";
        return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", did, "txId", txId,
                "metadataDigest", digest, "transactionValid", valid, "metadataMatches", matches, "status", status, "errorCode", errorCode);
    }
    private static boolean matches(Map<String, Object> doc, String did, String metadata) {
        return did.equals(doc.get("id")) && metadata.equals(doc.get("metadata")) && !Boolean.TRUE.equals(doc.get("deactivated"));
    }
    private static void validateTransaction(String txId, String nonce) {
        if (!txId.matches("[0-9a-f]{64}")) throw new BridgeException(400, "INVALID_TX_ID");
        if (!nonce.matches("[0-9a-f]{48}")) throw new BridgeException(400, "INVALID_NONCE");
    }
}
