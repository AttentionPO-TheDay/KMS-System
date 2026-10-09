package com.kms.fabricdid;

import com.yunphant.yunid.sdk.entity.Document;
import com.yunphant.yunid.sdk.exception.DidSdkException;
import com.yunphant.yunid.sdk.handler.DidHandler;
import com.yunphant.yunid.sdk.helper.NetworkHolder;
import com.yunphant.yunid.sdk.req.DocumentReq;
import com.yunphant.yunid.sdk.resp.TransactionResp;
import com.yunphant.yunid.sdk.resp.TxResp;
import org.hyperledger.fabric.sdk.helper.Utils;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Map;

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
        catch (Exception | LinkageError e) { throw new BridgeException(503, "SDK_INITIALIZATION_FAILED"); }
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
            if (Integer.valueOf(400001).equals(e.getErrorCode())) throw new BridgeException(404, "NOT_FOUND_OR_DEACTIVATED");
            throw new BridgeException(502, "DID_READ_FAILED");
        }
    }
    @Override public String transactionId(String nonce) {
        return NetworkHolder.getContract("DidController").createTransaction("createDidDocument", Utils.toByteString(nonce)).getTransactionId();
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
    @Override public Boolean transactionValid(String txId) {
        try {
            TransactionResp response = handler.getTransactionStateById(txId);
            if (response == null || !txId.equals(response.getTxId())) return null;
            return response.getValid();
        } catch (Exception e) { return null; }
    }
}
