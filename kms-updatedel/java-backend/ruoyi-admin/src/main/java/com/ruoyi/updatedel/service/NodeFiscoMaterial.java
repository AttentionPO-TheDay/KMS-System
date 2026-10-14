package com.ruoyi.updatedel.service;

import com.ruoyi.common.utils.ChainPublicMaterial;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

/** Public registration snapshot only; no private keys or device secrets. */
public final class NodeFiscoMaterial {
    public final String nodeId, algorithm, keyRef, material, publicHash;
    public final BigInteger chainKeyId, version;

    public NodeFiscoMaterial(Map<String, Object> input) {
        nodeId = text(input, "nodeId");
        algorithm = text(input, "algorithm");
        if (!java.util.Arrays.asList("SM2", "SSCL", "KYBER", "FALCON", "FALCON_CL_V1").contains(algorithm)) throw new IllegalArgumentException("INVALID_ALGORITHM");
        String keyId = text(input, "keyId");
        if (!nodeId.matches("[^/]{1,64}") || !keyId.matches("[^/]{1,64}")) throw new IllegalArgumentException("INVALID_KEY_REFERENCE");
        version = new BigInteger(text(input, "keyVersion"));
        if (version.signum() <= 0 || version.bitLength() > 32) throw new IllegalArgumentException("INVALID_VERSION");
        keyRef = "node/" + nodeId + "/" + algorithm + "/" + keyId + "/" + version;
        // Separate numeric space from legacy keymanage Long IDs; immutable per keyRef/version.
        chainKeyId = new BigInteger(sha256(keyRef), 16).setBit(255);
        publicHash = text(input, "publicKeyHash");
        if (!publicHash.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("INVALID_PUBLIC_HASH");
        material = text(input, "publicMaterial");
        ChainPublicMaterial.requireSmall(material);
        if (!(material.equals("sha256:" + publicHash) || sha256(material).equals(publicHash))) throw new IllegalArgumentException("PUBLIC_HASH_MISMATCH");
    }

    private static String text(Map<String, Object> input, String field) {
        Object value = input.get(field);
        if (!(value instanceof String) || ((String) value).isEmpty()) throw new IllegalArgumentException("INVALID_" + field);
        return (String) value;
    }

    public static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : digest) hex.append(String.format("%02x", b & 255));
            return hex.toString();
        } catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }

    public static org.fisco.bcos.sdk.transaction.model.po.RawTransaction unsignedTransaction(org.fisco.bcos.sdk.client.Client client, String contract, String data) {
        return new org.fisco.bcos.sdk.transaction.builder.TransactionBuilderService(client).createTransaction(
            org.fisco.bcos.sdk.transaction.model.gas.DefaultGasProvider.GAS_PRICE,
            org.fisco.bcos.sdk.transaction.model.gas.DefaultGasProvider.GAS_LIMIT,
            contract, data, BigInteger.ZERO,
            new BigInteger(client.getClientNodeVersion().getNodeVersion().getChainId()),
            BigInteger.valueOf(client.getGroupId()), "");
    }

    /** The node indexes the hash WITH the signature, not the hash used for signing. */
    public static String signedTransactionHash(org.fisco.bcos.sdk.crypto.CryptoSuite suite, String signed) {
        if (signed == null || signed.length() > 65536 || !signed.matches("(?:0x)?(?:[0-9a-fA-F]{2})+")) {
            throw new IllegalArgumentException("INVALID_SIGNED_TRANSACTION");
        }
        return "0x" + org.bouncycastle.util.encoders.Hex.toHexString(
            suite.hash(org.fisco.bcos.sdk.utils.Numeric.hexStringToByteArray(signed)));
    }
}
