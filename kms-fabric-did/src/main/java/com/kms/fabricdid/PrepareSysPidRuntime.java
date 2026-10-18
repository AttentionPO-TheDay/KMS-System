package com.kms.fabricdid;

import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;
import org.bouncycastle.asn1.x509.Certificate;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** 从供应方资料准备独立本机运行目录；只落盘，不连接网络或提交交易。 */
public final class PrepareSysPidRuntime {
    private PrepareSysPidRuntime() { }
    public static void main(String[] args) {
        try {
            if (args.length != 6) throw new IllegalArgumentException("USAGE: <sdk-yaml> <new-runtime-dir> <channel> <chaincode> <method> <sysPid-file>");
            Path source = Paths.get(args[0]).toAbsolutePath().normalize();
            Path runtime = Paths.get(args[1]).toAbsolutePath().normalize();
            if (Files.exists(runtime)) throw new IllegalArgumentException("RUNTIME_ALREADY_EXISTS");
            String channel = args[2], chaincode = args[3], method = args[4];
            if (!channel.matches("[a-zA-Z0-9_-]+") || !chaincode.matches("[a-zA-Z0-9_-]+") || !method.matches("[a-zA-Z]+"))
                throw new IllegalArgumentException("INVALID_TARGET_PARAMETERS");
            Map<String, Object> network;
            try (InputStream in = Files.newInputStream(source)) { network = new Yaml(new SafeConstructor()).load(in); }
            Map<String, Object> channelConfig = object(object(network, "channels"), channel);
            Map<String, Object> client = object(network, "client");
            String organization = string(client, "organization");
            Map<String, Object> org = object(object(network, "organizations"), organization);
            String certificate = string(object(org, "signedCert"), "pem");
            String privateKey = string(object(org, "adminPrivateKey"), "pem");
            // 保留证书的公钥作为原 bindings 配置所需的只读公钥文件；SysPid 文档另行生成管理密钥。
            byte[] certBytes = Base64.getMimeDecoder().decode(certificate.replace("-----BEGIN CERTIFICATE-----", "").replace("-----END CERTIFICATE-----", ""));
            byte[] spki = Certificate.getInstance(certBytes).getSubjectPublicKeyInfo().getEncoded("DER");
            String publicPem = "-----BEGIN PUBLIC KEY-----\n" + Base64.getMimeEncoder(64, new byte[] {10}).encodeToString(spki) + "\n-----END PUBLIC KEY-----\n";
            String sysPid = new String(Files.readAllBytes(Paths.get(args[5])), StandardCharsets.UTF_8).trim();
            StringBuilder certHex = new StringBuilder();
            for (byte value : spki) certHex.append(String.format("%02x", value & 255));
            if (!certHex.toString().equalsIgnoreCase(sysPid)) throw new IllegalArgumentException("SOURCE_CERTIFICATE_SYSPID_MISMATCH");
            // 新 YAML 的两个公网 url 缩进为节点的同级字段；只在运行副本中归位，原文件不修改。
            Map<String, Object> orderers = object(network, "orderers"), peers = object(network, "peers");
            Map<String, Object> orderer = new LinkedHashMap<>(object(orderers, "orderer-0-baas1"));
            Map<String, Object> peer = new LinkedHashMap<>(object(peers, "peer-1-baas1"));
            if (!orderer.containsKey("url")) orderer.put("url", string(orderers, "url"));
            if (!peer.containsKey("url")) peer.put("url", string(peers, "url"));
            if (!string(orderer, "url").startsWith("grpcs://") || !string(peer, "url").startsWith("grpcs://"))
                throw new IllegalArgumentException("TLS_ENDPOINT_REQUIRED");
            Map<String, Object> selected = new LinkedHashMap<>();
            selected.put("name", network.get("name")); selected.put("version", network.get("version"));
            selected.put("client", client);
            Map<String, Object> selectedChannel = new LinkedHashMap<>();
            selectedChannel.put("orderers", Collections.singletonList("orderer-0-baas1"));
            selectedChannel.put("peers", Collections.singletonMap("peer-1-baas1", object(object(channelConfig, "peers"), "peer-1-baas1")));
            selected.put("channels", Collections.singletonMap(channel, selectedChannel));
            selected.put("organizations", Collections.singletonMap(organization, Json.map("mspid", string(org, "mspid"), "peers", Collections.singletonList("peer-1-baas1"))));
            selected.put("orderers", Collections.singletonMap("orderer-0-baas1", orderer));
            selected.put("peers", Collections.singletonMap("peer-1-baas1", peer));
            SysPidService.secureDirectory(runtime);
            SysPidService.secureDirectory(runtime.resolve("work"));
            SysPidService.save(runtime.resolve("connection.json"), Json.encode(selected));
            SysPidService.save(runtime.resolve("application-cert.pem"), certificate);
            SysPidService.save(runtime.resolve("application-key.pem"), privateKey);
            SysPidService.save(runtime.resolve("controller-public.pem"), publicPem);
            String properties = "networkConfigPath=" + propertyPath(runtime.resolve("connection.json"))
                    + "\ncertificatePath=" + propertyPath(runtime.resolve("application-cert.pem"))
                    + "\nprivateKeyPath=" + propertyPath(runtime.resolve("application-key.pem"))
                    + "\nchannelName=" + channel + "\nchaincodeId=" + chaincode + "\nmethodId=" + method
                    + "\nmspId=" + string(org, "mspid") + "\nuserName=didadmin\nencryption=SM2\ntimeOut=30\n";
            SysPidService.save(runtime.resolve("fabric.config.properties"), properties);
            SysPidService.save(runtime.resolve("gm-sdk.properties"), "org.hyperledger.fabric.sdk.crypto.default_crypto_suite_factory=org.hyperledger.fabric.sdk.security.GMCryptoSuiteFactory\norg.hyperledger.fabric.sdk.hash_algorithm=SM3\norg.hyperledger.fabric.sdk.security_level=256\ncom.yunphant.yunchain.sdk.gmsign=true\ncom.yunphant.yunchain.sdk.gmtls=true\n");
            byte[] token = new byte[32]; new SecureRandom().nextBytes(token);
            Map<String, Object> env = Json.map("KMS_CHAIN_WRITES_ENABLED", "false", "FABRIC_DID_ENABLED", "true",
                    "FABRIC_DID_WRITE_ENABLED", "false", "FABRIC_DID_CREATE_POLICY_APPROVED", "false",
                    "FABRIC_DID_CHAIN_ID", "vendor-" + channel, "FABRIC_DID_METHOD_ID", method,
                    "INTERNAL_TOKEN", Base64.getEncoder().encodeToString(token),
                    "FABRIC_DID_PROPERTIES_FILE", runtime.resolve("fabric.config.properties").toString(),
                    "FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE", runtime.resolve("controller-public.pem").toString(),
                    "FABRIC_DID_SYSPID_RECORDS_DIR", runtime.resolve("records").toString());
            SysPidService.save(runtime.resolve("bridge.env.json"), Json.encode(env));
            System.out.println(Json.encode(Json.map("prepared", true, "submitted", false, "runtime", runtime.toString(),
                    "channelName", channel, "chaincodeId", chaincode, "methodId", method,
                    "orderer", orderer.get("url"), "peer", peer.get("url"), "sourceCertificateMatchesSysPid", true)));
        } catch (Exception e) {
            System.err.println(Json.encode(Json.map("errorCode", "RUNTIME_PREPARATION_FAILED", "exceptionType", e.getClass().getSimpleName())));
            System.exit(1);
        }
    }
    private static String propertyPath(Path path) {
        // java.util.Properties 读取 ISO-8859-1，Unicode 路径必须转义；避免中文目录被误读。
        StringBuilder out = new StringBuilder();
        for (char value : path.toString().replace('\\', '/').toCharArray()) {
            if (value > 127) out.append(String.format("\\u%04x", (int) value)); else out.append(value);
        }
        return out.toString();
    }
    @SuppressWarnings("unchecked") private static Map<String, Object> object(Map<String, Object> parent, String name) {
        Object value = parent.get(name);
        if (!(value instanceof Map)) throw new IllegalArgumentException("INVALID_CONFIGURATION_STRUCTURE");
        return (Map<String, Object>) value;
    }
    private static String string(Map<String, Object> parent, String name) {
        Object value = parent.get(name);
        if (!(value instanceof String) || ((String) value).isEmpty()) throw new IllegalArgumentException("MISSING_CONFIGURATION_VALUE");
        return (String) value;
    }
}
