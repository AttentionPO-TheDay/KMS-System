package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

final class Binding {
    static final Set<String> FIELDS = new HashSet<>(Arrays.asList("schemaVersion", "namespace", "eventId", "nodeId", "algorithm", "keyId", "keyVersion", "publicKey", "publicKeyHash", "status", "revision", "eventType", "recordedAt"));
    final Map<String, Object> metadata = new TreeMap<>();
    final String json, digest, did;
    Binding(JsonNode input, BridgeConfig config) {
        fields(input, FIELDS);
        int schema = integer(input, "schemaVersion");
        if (schema != 1) throw new BridgeException(400, "UNSUPPORTED_SCHEMA");
        metadata.put("schemaVersion", schema);
        for (String name : Arrays.asList("namespace", "eventId", "nodeId", "algorithm", "keyId", "publicKey", "publicKeyHash", "status", "eventType", "recordedAt"))
            metadata.put(name, Json.text(input, name));
        metadata.put("keyVersion", integer(input, "keyVersion"));
        metadata.put("revision", integer(input, "revision"));
        if (!config.namespace.equals(metadata.get("namespace"))) throw new BridgeException(400, "FOREIGN_NAMESPACE");
        member("algorithm", "SM2", "SSCL", "KYBER", "FALCON");
        member("status", "ACTIVE", "RETIRED", "REVOKED");
        member("eventType", "REGISTERED", "ROTATED", "REVOKED");
        if ("REVOKED".equals(metadata.get("eventType")) != "REVOKED".equals(metadata.get("status")))
            throw new BridgeException(400, "STATUS_EVENT_MISMATCH");
        String publicKey = (String) metadata.get("publicKey");
        // 哈希口径与登记表相同：存储字符串的 UTF-8，而不是解码后的密码学字节。
        if (!publicKey.equals(publicKey.trim()) || publicKey.contains("PRIVATE KEY")) throw new BridgeException(400, "INVALID_PUBLIC_KEY");
        if (!Json.digest(publicKey).equals(metadata.get("publicKeyHash"))) throw new BridgeException(400, "PUBLIC_KEY_HASH_MISMATCH");
        try {
            String time = (String) metadata.get("recordedAt");
            try { LocalDateTime.parse(time); } catch (Exception e) { OffsetDateTime.parse(time); }
        } catch (Exception e) { throw new BridgeException(400, "INVALID_RECORDED_AT"); }
        json = Json.encode(metadata);
        if (json.getBytes(StandardCharsets.UTF_8).length > config.maxMetadataBytes) throw new BridgeException(400, "METADATA_TOO_LARGE");
        digest = Json.digest(json);
        // 标识包含应用命名空间和完整绑定摘要；不覆盖外来 DID，不把任意业务 keyId 当作 DID。
        did = "did:" + config.methodId + ":" + config.namespace + ":binding:" + digest;
    }
    private void member(String field, String... valid) {
        if (!Arrays.asList(valid).contains(metadata.get(field))) throw new BridgeException(400, "INVALID_FIELD", field);
    }
    private static int integer(JsonNode input, String name) {
        JsonNode value = input.get(name);
        if (value == null || !value.isIntegralNumber() || !value.canConvertToInt() || value.intValue() < 1) throw new BridgeException(400, "INVALID_FIELD", name);
        return value.intValue();
    }
    static void fields(JsonNode input, Set<String> allowed) {
        if (input == null || !input.isObject()) throw new BridgeException(400, "INVALID_JSON_OBJECT");
        Iterator<String> names = input.fieldNames();
        while (names.hasNext()) if (!allowed.contains(names.next())) throw new BridgeException(400, "UNKNOWN_FIELD");
    }
}
