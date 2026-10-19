package com.kms.fabricdid;

import org.bouncycastle.asn1.x500.X500Name;
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder;
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.yaml.snakeyaml.Yaml;
import java.io.InputStream;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.Date;
import java.util.Map;
import java.util.Properties;
import static org.junit.Assert.*;

public class PrepareSysPidRuntimeTest {
    private Path root, source, target, sysPid, runtime;
    private Map<String, Object> network;
    private String settings;

    @Before public void setup() throws Exception {
        root = Files.createTempDirectory("did-runtime-test-");
        source = root.resolve("sdk.yml"); target = root.resolve("target.properties");
        sysPid = root.resolve("sys-pid.txt"); runtime = root.resolve("新通道");
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA"); generator.initialize(1024);
        KeyPair key = generator.generateKeyPair();
        X500Name name = new X500Name("CN=OFFLINE-TEST");
        byte[] certificate = new JcaX509v3CertificateBuilder(name, BigInteger.ONE,
                new Date(0), new Date(4102444800000L), name, key.getPublic())
                .build(new JcaContentSignerBuilder("SHA256withRSA").build(key.getPrivate())).getEncoded();
        String pem = "-----BEGIN CERTIFICATE-----\n" + Base64.getEncoder().encodeToString(certificate) + "\n-----END CERTIFICATE-----\n";
        StringBuilder hex = new StringBuilder();
        for (byte value : key.getPublic().getEncoded()) hex.append(String.format("%02x", value & 255));
        Files.write(sysPid, hex.toString().getBytes(StandardCharsets.UTF_8));
        Map<String, Object> node = Json.map("url", "grpcs://192.168.11.234:30034",
                "grpcOptions", Json.map("ssl-target-name-override", "orderer-0-baas1"),
                "tlsCACerts", Json.map("pem", "OFFLINE_CA_FIXTURE"));
        network = Json.map("name", "offline", "version", "1.0", "client", Json.map("organization", "baas1"),
                "channels", Json.map("didchannel4", Json.map("orderers", Arrays.asList("orderer-0-baas1"),
                        "peers", Json.map("peer-1-baas1", Json.map("endorsingPeer", true)))),
                "organizations", Json.map("baas1", Json.map("mspid", "baas1", "signedCert", Json.map("pem", pem),
                        "adminPrivateKey", Json.map("pem", "OFFLINE_KEY_FIXTURE"))),
                "orderers", Json.map("orderer-0-baas1", node),
                "peers", Json.map("peer-1-baas1", Json.map("url", "grpcs://192.168.11.234:30039",
                        "grpcOptions", Json.map("ssl-target-name-override", "peer-1-baas1"),
                        "tlsCACerts", Json.map("pem", "OFFLINE_CA_FIXTURE"))));
        writeSource();
        settings = "channelName=didchannel4\nchaincodeId=didchaincode4\nmethodId=yunId\nuserName=peer-1-baas1\nmspId=baas1\n"
                + "ordererUrl=grpcs://122.224.205.114:18134\npeerUrl=grpcs://122.224.205.114:18139\n";
        writeTarget();
    }
    private void writeSource() throws Exception { Files.write(source, new Yaml().dump(network).getBytes(StandardCharsets.UTF_8)); }
    private void writeTarget() throws Exception { Files.write(target, settings.getBytes(StandardCharsets.UTF_8)); }
    private Map<String, Object> prepare() throws Exception {
        return PrepareSysPidRuntime.prepare(new String[] {source.toString(), runtime.toString(), target.toString(), sysPid.toString()});
    }
    @After public void cleanup() throws Exception {
        try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
            for (Path path : (Iterable<Path>) paths.sorted(Collections.reverseOrder())::iterator) Files.delete(path);
        }
    }
    @Test public void newTargetKeepsIdentityTlsAndReadOnlyDefaults() throws Exception {
        byte[] original = Files.readAllBytes(source);
        Map<String, Object> result = prepare();
        assertEquals(false, result.get("submitted")); assertEquals("yunId", result.get("methodId"));
        Properties properties = new Properties();
        try (InputStream in = Files.newInputStream(runtime.resolve("fabric.config.properties"))) { properties.load(in); }
        assertEquals("peer-1-baas1", properties.getProperty("userName"));
        assertEquals("didchannel4", properties.getProperty("channelName"));
        assertEquals("didchaincode4", properties.getProperty("chaincodeId"));
        assertEquals(runtime.resolve("connection.json").toString().replace('\\', '/'), properties.getProperty("networkConfigPath"));
        com.fasterxml.jackson.databind.JsonNode selected = Json.MAPPER.readTree(Files.readAllBytes(runtime.resolve("connection.json")));
        assertEquals("grpcs://122.224.205.114:18134", selected.at("/orderers/orderer-0-baas1/url").asText());
        assertEquals("grpcs://122.224.205.114:18139", selected.at("/peers/peer-1-baas1/url").asText());
        assertEquals("orderer-0-baas1", selected.at("/orderers/orderer-0-baas1/grpcOptions/ssl-target-name-override").asText());
        assertEquals("OFFLINE_CA_FIXTURE", selected.at("/peers/peer-1-baas1/tlsCACerts/pem").asText());
        com.fasterxml.jackson.databind.JsonNode env = Json.MAPPER.readTree(Files.readAllBytes(runtime.resolve("bridge.env.json")));
        for (String flag : new String[] {"KMS_CHAIN_WRITES_ENABLED", "FABRIC_DID_WRITE_ENABLED", "FABRIC_DID_CREATE_POLICY_APPROVED"})
            assertEquals("false", env.get(flag).asText());
        assertEquals("vendor-didchannel4", env.get("FABRIC_DID_CHAIN_ID").asText());
        assertArrayEquals(original, Files.readAllBytes(source));
        assertFalse(Files.exists(runtime.resolve("records")));
    }
    @Test public void legacySixArgumentsStillWork() throws Exception {
        PrepareSysPidRuntime.prepare(new String[] {source.toString(), runtime.toString(), "didchannel4", "didchaincode4", "yunId", sysPid.toString()});
        assertTrue(new String(Files.readAllBytes(runtime.resolve("fabric.config.properties")), StandardCharsets.UTF_8).contains("userName=didadmin\n"));
    }
    @Test public void selectedOrdererUsesItsOwnYamlTlsIdentity() throws Exception {
        ((Map<String, Object>) network.get("orderers")).put("orderer-1-baas1", Json.map(
                "url", "grpcs://192.168.11.234:30036",
                "grpcOptions", Json.map("ssl-target-name-override", "orderer-1-baas1"),
                "tlsCACerts", Json.map("pem", "ORDERER_1_CA_FIXTURE")));
        ((Map<String, Object>) ((Map<?, ?>) network.get("channels")).get("didchannel4"))
                .put("orderers", Arrays.asList("orderer-0-baas1", "orderer-1-baas1"));
        settings += "ordererName=orderer-1-baas1\n"; writeSource(); writeTarget();
        assertEquals("orderer-1-baas1", prepare().get("ordererName"));
        com.fasterxml.jackson.databind.JsonNode selected = Json.MAPPER.readTree(Files.readAllBytes(runtime.resolve("connection.json")));
        assertEquals("orderer-1-baas1", selected.at("/channels/didchannel4/orderers/0").asText());
        assertEquals("orderer-1-baas1", selected.at("/orderers/orderer-1-baas1/grpcOptions/ssl-target-name-override").asText());
        assertEquals("ORDERER_1_CA_FIXTURE", selected.at("/orderers/orderer-1-baas1/tlsCACerts/pem").asText());
        assertEquals("grpcs://122.224.205.114:18134", selected.at("/orderers/orderer-1-baas1/url").asText());
        assertFalse(selected.get("orderers").has("orderer-0-baas1"));
    }
    @Test public void ordererOutsideSelectedChannelRejected() throws Exception {
        settings += "ordererName=orderer-1-baas1\n"; writeTarget();
        expectFailure("ORDERER_NOT_IN_CHANNEL");
    }
    @Test public void insecureEndpointRejectedBeforeWriting() throws Exception {
        settings = settings.replace("ordererUrl=grpcs://", "ordererUrl=grpc://"); writeTarget();
        expectFailure("TLS_ENDPOINT_REQUIRED");
    }
    @Test public void differentMspRejectedBeforeWriting() throws Exception {
        settings = settings.replace("mspId=baas1", "mspId=other"); writeTarget();
        expectFailure("SOURCE_MSP_MISMATCH");
    }
    @Test public void missingPeerNotInvented() throws Exception {
        ((Map<?, ?>) ((Map<?, ?>) network.get("channels")).get("didchannel4")).remove("peers"); writeSource();
        expectFailure("INVALID_CONFIGURATION_STRUCTURE");
    }
    @Test public void missingUserRejectedBeforeWriting() throws Exception {
        settings = settings.replace("userName=peer-1-baas1\n", ""); writeTarget();
        expectFailure("MISSING_TARGET_PARAMETER");
    }
    @Test public void existingRuntimeIsNeverOverwritten() throws Exception {
        prepare(); byte[] saved = Files.readAllBytes(runtime.resolve("bridge.env.json"));
        try { prepare(); fail("Expected refusal to overwrite"); }
        catch (IllegalArgumentException expected) { assertEquals("RUNTIME_ALREADY_EXISTS", expected.getMessage()); }
        assertArrayEquals(saved, Files.readAllBytes(runtime.resolve("bridge.env.json")));
    }
    private void expectFailure(String message) throws Exception {
        try { prepare(); fail("Expected " + message); }
        catch (IllegalArgumentException expected) { assertEquals(message, expected.getMessage()); }
        assertFalse(Files.exists(runtime));
    }
}
