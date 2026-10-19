package com.kms.fabricdid;

import java.util.Map;

interface DidSdk {
    Map<String, Object> newTransaction();
    Map<String, Object> read(String did);
    String transactionId(String nonce);
    default boolean matchesRecordedTransactionId(String nonce, String txId) { return txId.equals(transactionId(nonce)); }
    String create(String did, String metadata, String nonce);
    Map<String, String> newSystemKey();
    String createSystemIdentifier(String did, String sysPid, String publicKey, String nonce);
    Boolean transactionValid(String txId);
    default boolean transactionAbsent(String txId) { return false; }
    interface Factory { DidSdk create(); }
}
