package com.kms.fabricdid;

import java.util.Map;

interface DidSdk {
    Map<String, Object> newTransaction();
    Map<String, Object> read(String did);
    String transactionId(String nonce);
    String create(String did, String metadata, String nonce);
    Boolean transactionValid(String txId);
    interface Factory { DidSdk create(); }
}
