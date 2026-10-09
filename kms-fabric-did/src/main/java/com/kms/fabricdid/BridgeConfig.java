package com.kms.fabricdid;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;

final class BridgeConfig {
    final boolean enabled, writeEnabled, policyApproved;
    final String chainId, namespace, methodId, internalToken, host;
    final int port, maxMetadataBytes;
    final Properties fabric = new Properties();
    final List<String> missingFields = new ArrayList<>();
    final Path propertiesPath, controllerPublicKeyPath;

    BridgeConfig(Map<String, String> env) {
        enabled = bool(env, "FABRIC_DID_ENABLED");
        writeEnabled = bool(env, "FABRIC_DID_WRITE_ENABLED");
        policyApproved = bool(env, "FABRIC_DID_CREATE_POLICY_APPROVED");
        chainId = env.getOrDefault("FABRIC_DID_CHAIN_ID", "");
        namespace = env.getOrDefault("FABRIC_DID_NAMESPACE", "kms-key-binding-v1");
        methodId = env.getOrDefault("FABRIC_DID_METHOD_ID", "");
        internalToken = env.getOrDefault("INTERNAL_TOKEN", "");
        host = env.getOrDefault("FABRIC_DID_HOST", "127.0.0.1");
        port = Integer.parseInt(env.getOrDefault("FABRIC_DID_PORT", "8095"));
        maxMetadataBytes = Integer.parseInt(env.getOrDefault("FABRIC_DID_MAX_METADATA_BYTES", "65536"));
        Path cwd = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize();
        Path parent = cwd.getParent();
        propertiesPath = path(env.get("FABRIC_DID_PROPERTIES_FILE"), cwd);
        controllerPublicKeyPath = path(env.get("FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE"), cwd);
        require("FABRIC_DID_CHAIN_ID", !chainId.trim().isEmpty());
        require("FABRIC_DID_METHOD_ID", methodId.matches("[a-z0-9]+"));
        require("FABRIC_DID_NAMESPACE", namespace.matches("[a-zA-Z0-9_-]{1,80}"));
        require("INTERNAL_TOKEN", !internalToken.isEmpty());
        // SDK 固定从工作目录父目录取配置；不偷偷复制凭据，也不修改进程全局工作目录。
        require("FABRIC_DID_PROPERTIES_FILE", propertiesPath != null && parent != null
                && propertiesPath.equals(parent.resolve("fabric.config.properties")) && readable(propertiesPath));
        if (!missingFields.contains("FABRIC_DID_PROPERTIES_FILE")) {
            try (InputStream stream = Files.newInputStream(propertiesPath)) { fabric.load(stream); }
            catch (Exception e) { require("FABRIC_DID_PROPERTIES_FILE", false); }
        }
        for (String key : new String[] {"networkConfigPath", "certificatePath", "privateKeyPath"}) {
            Path file = path(fabric.getProperty(key), cwd);
            require(key, readable(file));
        }
        for (String key : new String[] {"channelName", "mspId", "chaincodeId", "userName"})
            require(key, !fabric.getProperty(key, "").trim().isEmpty());
        require("encryption", "SM2".equalsIgnoreCase(fabric.getProperty("encryption")));
        String timeout = fabric.getProperty("timeOut", "");
        require("timeOut", timeout.matches("[1-9][0-9]{0,5}"));
        Path gmConfig = path(System.getProperty("fabricSDK.configuration"), cwd);
        require("fabricSDK.configuration", readable(gmConfig));
        Properties gm = new Properties();
        if (readable(gmConfig)) {
            try (InputStream stream = Files.newInputStream(gmConfig)) { gm.load(stream); }
            catch (Exception e) { require("fabricSDK.configuration", false); }
        }
        require("gmCryptoSuiteFactory", "org.hyperledger.fabric.sdk.security.GMCryptoSuiteFactory".equals(
                gm.getProperty("org.hyperledger.fabric.sdk.crypto.default_crypto_suite_factory")));
        require("gmHashAlgorithm", "SM3".equals(gm.getProperty("org.hyperledger.fabric.sdk.hash_algorithm")));
        require("gmSecurityLevel", "256".equals(gm.getProperty("org.hyperledger.fabric.sdk.security_level")));
        require("FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE", readable(controllerPublicKeyPath));
    }
    private void require(String name, boolean valid) { if (!valid && !missingFields.contains(name)) missingFields.add(name); }
    private static boolean bool(Map<String, String> env, String key) { return "true".equalsIgnoreCase(env.get(key)); }
    private static Path path(String value, Path cwd) {
        if (value == null || value.trim().isEmpty()) return null;
        try { return cwd.resolve(value).toAbsolutePath().normalize(); }
        catch (Exception e) { return null; }
    }
    private static boolean readable(Path path) { return path != null && Files.isRegularFile(path) && Files.isReadable(path); }
    boolean configured() { return missingFields.isEmpty(); }
    String status() {
        if (!enabled) return "DISABLED";
        if (!configured()) return "NOT_CONFIGURED";
        return writeEnabled && policyApproved ? "READY" : "READY_READ_ONLY";
    }
    void requireRead() {
        if (!enabled) throw new BridgeException(503, "DISABLED");
        if (!configured()) throw new BridgeException(503, "NOT_CONFIGURED");
    }
    void requireWrite() {
        requireRead();
        if (!writeEnabled) throw new BridgeException(403, "WRITE_DISABLED");
        if (!policyApproved) throw new BridgeException(409, "CHAIN_POLICY_NOT_APPROVED");
    }
}
