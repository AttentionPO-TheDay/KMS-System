package com.kms.fabricdid;

import com.yunphant.yunid.sdk.entity.Document;
import com.yunphant.yunid.sdk.exception.DidSdkException;
import com.yunphant.yunid.sdk.handler.DidHandler;
import com.yunphant.yunid.sdk.helper.NetworkHolder;
import com.yunphant.yunid.sdk.req.DocumentReq;
import com.yunphant.yunid.sdk.resp.TransactionResp;
import com.yunphant.yunid.sdk.resp.TxResp;
import com.yunphant.core.domain.YunKeyPair;
import com.yunphant.core.service.impl.KmsServiceImpl;
import org.hyperledger.fabric.sdk.helper.Utils;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Map;
import java.util.HashMap;

final class VendorDidSdk implements DidSdk {
    private final DidHandler handler;
    private final String controllerPublicKey;
    VendorDidSdk(BridgeConfig config) {
        config.requireRead();
        try {
            controllerPublicKey = new String(Files.readAllBytes(config.controllerPublicKeyPath), StandardCharsets.UTF_8);
            if (!controllerPublicKey.contains("-----BEGIN PUBLIC KEY-----") || controllerPublicKey.contains("PRIVATE KEY"))
                throw new BridgeException(503, "INVALID_CONTROLLER_PUBLIC_KEY");
            // NetworkHolder 和国密 provider 均为静态全局；只在隔离 JVM 首次授权访问时初始化。
            handler = new DidHandler();
        } catch (BridgeException e) { throw e; }
        catch (Exception | LinkageError e) { throw caused(503, "SDK_INITIALIZATION_FAILED", e); }
    }
    @Override public Map<String, Object> newTransaction() {
        TxResp tx = handler.genTxId();
        return Json.map("txId", tx.getTxId(), "nonce", tx.getNonce());
    }
    @Override public Map<String, Object> read(String did) {
        try {
            Document doc = handler.getDidDocument(did);
            if (doc == null) throw new BridgeException(502, "EMPTY_DID_RESPONSE");
            Map<String, Object> data = Json.MAPPER.convertValue(doc, Map.class);
            data.put("status", Boolean.TRUE.equals(doc.getDeactivated()) ? "DEACTIVATED" : "FOUND");
            return data;
        } catch (DidSdkException e) {
            // 供应方 400001 本身合并“不存在或已注销”；保留这个不确定性，不能冒充明确未找到。
            if (isMissingDidError(e)) throw new BridgeException(404, "NOT_FOUND_OR_DEACTIVATED");
            throw caused(502, "DID_READ_FAILED", e);
        }
    }
    @Override public String transactionId(String nonce) {
        return NetworkHolder.getContract("DidController").createTransaction("createDidDocument", Utils.toByteString(nonce)).getTransactionId();
    }
    @Override public boolean matchesRecordedTransactionId(String nonce, String txId) {
        org.hyperledger.fabric.sdk.transaction.TransactionContext context = NetworkHolder.getInstance().getChannel()
                .newTransactionContext(Utils.toByteString(nonce));
        return txId.equals(context.getTxID()) || matchesCreatorTransaction(txId, context.getNonce(), context.getIdentity(), context.getCryptoPrimitives());
    }
    static boolean matchesCreatorTransaction(String txId, com.google.protobuf.ByteString nonce,
            org.hyperledger.fabric.protos.msp.Identities.SerializedIdentity identity,
            org.hyperledger.fabric.sdk.security.CryptoSuite crypto) {
        // Gateway 的 PEMWriter 使用平台换行；仅兼容同一 MSP、同一证书的 LF/CRLF 序列化，不能接受其他身份。
        String lf = identity.getIdBytes().toStringUtf8().replace("\r\n", "\n");
        for (String pem : new String[] {lf, lf.replace("\n", "\r\n")}) {
            com.google.protobuf.ByteString creator = identity.toBuilder().setIdBytes(com.google.protobuf.ByteString.copyFromUtf8(pem)).build().toByteString();
            if (txId.equals(org.bouncycastle.util.encoders.Hex.toHexString(crypto.hash(nonce.concat(creator).toByteArray())))) return true;
        }
        return false;
    }
    @Override public String create(String did, String metadata, String nonce) {
        // 管理 SM2 公钥永远来自固定配置；业务四算法公钥只写入 metadata，不生成临时管理私钥。
        return handler.createDidDocument(documentRequest(did, metadata, controllerPublicKey), nonce);
    }
    static DocumentReq documentRequest(String did, String metadata, String controllerPublicKey) {
        DocumentReq request = new DocumentReq();
        request.setId(did);
        request.setPublicKey(controllerPublicKey);
        request.setMetadata(metadata);
        return request;
    }
    @Override public Map<String, String> newSystemKey() {
        return generateSystemKey();
    }
    static Map<String, String> generateSystemKey() {
        YunKeyPair pair = new KmsServiceImpl().genKey();
        Map<String, String> key = new HashMap<>();
        key.put("publicKey", pair.getPublicKey());
        key.put("privateKey", pair.getPrivateKey());
        return key;
    }
    @Override public String createSystemIdentifier(String did, String sysPid, String publicKey, String nonce) {
        return handler.createDidDocument(systemIdentifierRequest(did, sysPid, publicKey), nonce);
    }
    static DocumentReq systemIdentifierRequest(String did, String sysPid, String publicKey) {
        DocumentReq request = documentRequest(did, sysPid, publicKey);
        request.setAlsoKnownAs("ZHXUN_DID");
        return request;
    }
    void preflightSystemIdentifier(String did, String sysPid, String publicKey, String nonce) throws Exception {
        // 与 DidHandler 相同的文档字段，仅 evaluate 模拟请求；绝不 submit/广播到 orderer。
        Document document = systemIdentifierDocument(did, sysPid, publicKey);
        NetworkHolder.getContract("DidController").createTransaction("createDidDocument", Utils.toByteString(nonce))
                .evaluate(com.yunphant.yunid.sdk.contract.AbstractContract.toJSONString(document));
    }
    static Document systemIdentifierDocument(String did, String sysPid, String publicKey) {
        Document document = new Document();
        document.setId(did); document.setController(java.util.Collections.singletonList(did));
        document.setAlsoKnownAs("ZHXUN_DID"); document.setRole(com.yunphant.yunid.sdk.enums.DidRoleEnum.HOLDER.getCode());
        document.setDeactivated(false); document.setFrozen(false); document.setMetadata(sysPid);
        long now = System.currentTimeMillis(); document.setCreated(now); document.setUpdated(now);
        com.yunphant.yunid.sdk.entity.PublicKey key = new com.yunphant.yunid.sdk.entity.PublicKey();
        key.setId("key-" + com.yunphant.yunid.sdk.util.PemUtil.pemToSki(publicKey));
        key.setType(com.yunphant.yunid.sdk.enums.ProofSignatureEnum.SM2.getType());
        key.setController(did); key.setPublicKeyPem(publicKey); key.setExpired(0L);
        document.setVerificationMethod(java.util.Collections.singletonList(key));
        document.setAuthentication(java.util.Collections.singletonList(key));
        document.setAssertionMethod(java.util.Collections.singletonList(key));
        return document;
    }
    @Override public Boolean transactionValid(String txId) {
        try {
            TransactionResp response = handler.getTransactionStateById(txId);
            if (response == null || !txId.equals(response.getTxId())) return null;
            return response.getValid();
        } catch (Exception e) { SysPidCommand.diagnostics(e); return null; }
    }
    private static BridgeException caused(int status, String code, Throwable cause) {
        BridgeException error = new BridgeException(status, code);
        error.initCause(cause);
        return error;
    }
    @Override public boolean transactionAbsent(String txId) {
        try { handler.getTransactionStateById(txId); return false; }
        catch (DidSdkException e) {
            String message = e.getErrorMsg() == null ? e.getMessage() : e.getErrorMsg();
            return Integer.valueOf(900000).equals(e.getErrorCode()) && message != null
                    && message.contains("Failed to get transaction with id " + txId)
                    && message.contains("Entry not found in index");
        }
    }
    static boolean isMissingDidError(DidSdkException error) {
        // 实链 SDK 也会使用 String 构造器：errorCode/errorMsg=null，message="400001|DID不存在"。
        // 只识别完整的已知错误码前缀，绝不能把所有链/网络异常都当成 DID 不存在。
        return Integer.valueOf(400001).equals(error.getErrorCode())
                || (error.getErrorCode() == null && error.getMessage() != null && error.getMessage().startsWith("400001|"));
    }
}
