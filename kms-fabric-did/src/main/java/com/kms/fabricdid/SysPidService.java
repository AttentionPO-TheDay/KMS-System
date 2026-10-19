package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import org.bouncycastle.asn1.ASN1Primitive;
import org.bouncycastle.asn1.ASN1Sequence;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclEntryPermission;
import java.nio.file.attribute.AclEntryType;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumSet;
import java.util.Map;

/** CLA 系统标识独立上链，不复用业务密钥绑定的 DID 或 JSON metadata。 */
final class SysPidService {
    private final BridgeConfig config;
    private final DidSdk.Factory factory;
    private DidSdk instance;
    SysPidService(BridgeConfig config, DidSdk.Factory factory) { this.config = config; this.factory = factory; }
    private DidSdk sdk() {
        config.requireRead();
        if (instance == null) instance = factory.create();
        return instance;
    }
    synchronized Map<String, Object> onchain(JsonNode body) {
        config.requireWrite();
        return execute(body, true, false);
    }
    synchronized Map<String, Object> verify(JsonNode body) {
        config.requireRead();
        return execute(body, false, false);
    }
    synchronized Map<String, Object> retryUnrecordedTransaction(JsonNode body) {
        config.requireWrite();
        return execute(body, true, true);
    }
    private Map<String, Object> execute(JsonNode body, boolean submit, boolean explicitRetry) {
        Binding.fields(body, Collections.singleton("sysPid"));
        String sysPid = Json.text(body, "sysPid");
        String did = did(sysPid, config);
        if (config.sysPidRecordsPath == null) throw new BridgeException(503, "SYSPID_RECORDS_NOT_CONFIGURED");
        Path folder = config.sysPidRecordsPath.resolve(Json.digest(config.chainId + "\n" + did));
        try {
            if (!submit && !Files.isRegularFile(folder.resolve("record.json")))
                throw new BridgeException(404, "SYSPID_RECORD_NOT_FOUND");
            secureDirectory(config.sysPidRecordsPath);
            secureDirectory(folder);
            // 同一标识跨进程互斥；不能让两个 JVM 为同一个 DID 分配两套管理密钥和交易。
            try (FileChannel channel = FileChannel.open(folder.resolve("record.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE);
                 FileLock lock = channel.lock()) {
                Path record = folder.resolve("record.json");
                Map<String, Object> plan;
                if (Files.isRegularFile(record)) {
                    plan = Json.MAPPER.readValue(Files.readAllBytes(record), Map.class);
                    validatePlan(plan, did, sysPid);
                    // 已经开始提交的交易只核对，超时或进程重启后也不自动重发。
                    if (!submit) return verification(plan);
                    if (!"PREPARED".equals(plan.get("status"))) {
                        Map<String, Object> checked = verification(plan);
                        // 普通请求永不重发。只有操作员显式 retry 且账本明确返回原 txId 不存在时，恢复原计划。
                        if (!explicitRetry || !"PENDING_VERIFICATION".equals(checked.get("status"))
                                || checked.get("transactionValid") != null
                                || !("NOT_FOUND_OR_DEACTIVATED".equals(checked.get("errorCode")) || "NOT_FOUND".equals(checked.get("errorCode")))
                                || !sdk().transactionAbsent((String) plan.get("txId"))) return checked;
                        Object previous = plan.get("retryCount");
                        plan.put("retryCount", previous instanceof Number ? ((Number) previous).intValue() + 1 : 1);
                    }
                } else {
                    Map<String, Object> existing = readOrAbsent(did);
                    if (existing != null) {
                        if (!matches(existing, did, sysPid)) throw new BridgeException(409, "SYSPID_DOCUMENT_CONFLICT");
                        // 链上已有同一标识，但没有本地交易证据：不伪造 txId 或交易已核验状态。
                        return Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", did,
                                "sysPid", sysPid, "status", "EXISTS", "metadataMatches", true, "submitted", false);
                    }
                    Map<String, String> key = sdk().newSystemKey();
                    String publicKey = key.get("publicKey"), privateKey = key.get("privateKey");
                    if (publicKey == null || !publicKey.contains("-----BEGIN PUBLIC KEY-----")
                            || publicKey.contains("PRIVATE KEY") || privateKey == null || !privateKey.contains("PRIVATE KEY"))
                        throw new BridgeException(502, "INVALID_GENERATED_SYSTEM_KEY");
                    // 只保存在受限本地目录，避免 DID 创建后丢失管理私钥；绝不进入响应或 metadata。
                    save(folder.resolve("controller-private.pem"), privateKey);
                    Map<String, Object> tx = sdk().newTransaction();
                    String txId = String.valueOf(tx.get("txId")), nonce = String.valueOf(tx.get("nonce"));
                    if (!txId.matches("[0-9a-f]{64}") || !nonce.matches("[0-9a-f]{48}")
                            || !txId.equals(sdk().transactionId(nonce))) throw new BridgeException(502, "INVALID_SYSTEM_TRANSACTION");
                    plan = Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", did,
                            "sysPid", sysPid, "metadata", sysPid, "alsoKnownAs", "ZHXUN_DID", "publicKey", publicKey,
                            "txId", txId, "nonce", nonce, "status", "PREPARED", "submitted", false);
                    save(record, Json.encode(plan));
                }
                // 跨平台可核验已落账的旧身份序列化，但恢复提交必须仍产生原 txId，不能把新交易伪装成旧交易。
                if (!plan.get("txId").equals(sdk().transactionId((String) plan.get("nonce"))))
                    throw new BridgeException(409, "SYSPID_SIGNER_SERIALIZATION_CHANGED");
                // 必须在 SDK 调用前持久化不确定状态，不能将 createDidDocument 的 DID 返回值当回执。
                plan.put("status", "PENDING_VERIFICATION");
                plan.put("submitted", true);
                save(record, Json.encode(plan));
                try {
                    sdk().createSystemIdentifier(did, sysPid, (String) plan.get("publicKey"), (String) plan.get("nonce"));
                } catch (Exception e) {
                    Map<String, Object> result = verification(plan);
                    SysPidCommand.diagnostics(e);
                    if ("PENDING_VERIFICATION".equals(result.get("status"))) result.put("errorCode", "SUBMISSION_OUTCOME_UNKNOWN");
                    return result;
                }
                return verification(plan);
            }
        } catch (BridgeException e) { throw e; }
        catch (IOException e) { throw new BridgeException(503, "SYSPID_RECORD_STORAGE_FAILED"); }
    }
    static String did(String sysPid, BridgeConfig config) {
        if (sysPid.length() > config.maxMetadataBytes || !sysPid.matches("(?:[0-9a-fA-F]{2})+"))
            throw new BridgeException(400, "INVALID_SYS_PID");
        try {
            byte[] bytes = new byte[sysPid.length() / 2];
            for (int i = 0; i < bytes.length; i++) bytes[i] = (byte) Integer.parseInt(sysPid.substring(i * 2, i * 2 + 2), 16);
            ASN1Primitive value = ASN1Primitive.fromByteArray(bytes);
            if (!(value instanceof ASN1Sequence) || !Arrays.equals(bytes, value.getEncoded("DER")))
                throw new IllegalArgumentException();
        } catch (Exception e) { throw new BridgeException(400, "INVALID_SYS_PID"); }
        String method = config.fabric.getProperty("methodId", "");
        String channel = config.fabric.getProperty("channelName", "");
        if (!method.matches("[a-zA-Z]+")) throw new BridgeException(503, "SYSPID_METHOD_ID_NOT_CONFIGURED");
        if (!method.equals(config.methodId)) throw new BridgeException(503, "SYSPID_METHOD_ID_MISMATCH");
        if (!channel.matches("[a-zA-Z0-9_-]+")) throw new BridgeException(503, "SYSPID_CHANNEL_NOT_CONFIGURED");
        String did = "did:" + method + ":" + channel + ":zhxun-test" + sysPid;
        if (did.length() > 512) throw new BridgeException(400, "SYS_PID_TOO_LONG");
        return did;
    }
    private void validatePlan(Map<String, Object> plan, String did, String sysPid) {
        String txId = String.valueOf(plan.get("txId")), nonce = String.valueOf(plan.get("nonce"));
        if (!"FABRIC_DID".equals(plan.get("provider")) || !config.chainId.equals(plan.get("chainId"))
                || !did.equals(plan.get("did")) || !sysPid.equals(plan.get("metadata")) || !sysPid.equals(plan.get("sysPid"))
                || !"ZHXUN_DID".equals(plan.get("alsoKnownAs")) || !(plan.get("publicKey") instanceof String)
                || !((String) plan.get("publicKey")).contains("-----BEGIN PUBLIC KEY-----")
                || ((String) plan.get("publicKey")).contains("PRIVATE KEY")
                || !("PREPARED".equals(plan.get("status")) || "PENDING_VERIFICATION".equals(plan.get("status")))
                || !txId.matches("[0-9a-f]{64}") || !nonce.matches("[0-9a-f]{48}")
                || !sdk().matchesRecordedTransactionId(nonce, txId)) throw new BridgeException(409, "SYSPID_RECORD_MISMATCH");
    }
    private Map<String, Object> readOrAbsent(String did) {
        try { return sdk().read(did); }
        catch (BridgeException e) {
            if ("NOT_FOUND".equals(e.errorCode) || "NOT_FOUND_OR_DEACTIVATED".equals(e.errorCode)) return null;
            throw e;
        }
    }
    private Map<String, Object> verification(Map<String, Object> plan) throws IOException {
        String did = (String) plan.get("did"), sysPid = (String) plan.get("sysPid"), txId = (String) plan.get("txId");
        Boolean valid = sdk().transactionValid(txId), match = null;
        String error = null;
        try {
            Map<String, Object> document = sdk().read(did);
            match = matches(document, did, sysPid) && hasPublicKey(document, (String) plan.get("publicKey"));
        }
        catch (BridgeException e) { error = e.errorCode; }
        catch (Exception e) { error = "DID_READ_FAILED"; }
        String status = "PENDING_VERIFICATION";
        if (Boolean.FALSE.equals(valid)) { status = "FAILED"; error = "TRANSACTION_INVALID"; }
        else if (Boolean.FALSE.equals(match)) { status = "FAILED"; error = "SYSPID_DOCUMENT_MISMATCH"; }
        else if (Boolean.TRUE.equals(valid) && Boolean.TRUE.equals(match)) { status = "CONFIRMED"; error = null; }
        Map<String, Object> result = Json.map("provider", "FABRIC_DID", "chainId", config.chainId, "did", did, "sysPid", sysPid,
                "txId", txId, "status", status, "submitted", plan.get("submitted"), "transactionValid", valid,
                "metadataMatches", match, "errorCode", error);
        save(config.sysPidRecordsPath.resolve(Json.digest(config.chainId + "\n" + did)).resolve("verification.json"), Json.encode(result));
        return result;
    }
    private static boolean matches(Map<String, Object> doc, String did, String sysPid) {
        return did.equals(doc.get("id")) && sysPid.equals(doc.get("metadata"))
                && "ZHXUN_DID".equals(doc.get("alsoKnownAs")) && !Boolean.TRUE.equals(doc.get("deactivated"));
    }
    private static boolean hasPublicKey(Map<String, Object> doc, String publicKey) {
        Object methods = doc.get("verificationMethod");
        if (methods instanceof Iterable) for (Object value : (Iterable<?>) methods) {
            if (value instanceof Map && publicKey.replaceAll("\\s", "").equals(
                    String.valueOf(((Map<?, ?>) value).get("publicKeyPem")).replaceAll("\\s", ""))) return true;
        }
        return false;
    }
    static void secureDirectory(Path path) throws IOException {
        if (!Files.exists(path)) Files.createDirectories(path);
        if (Files.getFileAttributeView(path, PosixFileAttributeView.class) != null)
            Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rwx------"));
        else {
            AclFileAttributeView acl = Files.getFileAttributeView(path, AclFileAttributeView.class);
            if (acl == null) throw new IOException("Unsupported secure storage filesystem");
            AclEntry owner = AclEntry.newBuilder().setType(AclEntryType.ALLOW).setPrincipal(acl.getOwner())
                    .setPermissions(EnumSet.allOf(AclEntryPermission.class)).setFlags(
                            java.nio.file.attribute.AclEntryFlag.DIRECTORY_INHERIT,
                            java.nio.file.attribute.AclEntryFlag.FILE_INHERIT).build();
            acl.setAcl(Collections.singletonList(owner));
        }
    }
    static void save(Path path, String content) throws IOException {
        Path temporary = Files.createTempFile(path.getParent(), ".sys-pid-", ".tmp");
        try {
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                ByteBuffer bytes = ByteBuffer.wrap(content.getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) channel.write(bytes);
                channel.force(true);
            }
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temporary); }
    }
}
