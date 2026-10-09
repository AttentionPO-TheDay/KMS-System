package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.core.JsonParser;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;

final class Json {
    static final ObjectMapper MAPPER = new ObjectMapper()
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
            .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    private Json() { }
    static String encode(Object value) {
        try { return MAPPER.writeValueAsString(value); }
        catch (Exception e) { throw new IllegalArgumentException("INVALID_JSON"); }
    }
    static String digest(String text) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte b : hash) result.append(String.format("%02x", b & 255));
            return result.toString();
        } catch (Exception e) { throw new IllegalStateException("SHA256_UNAVAILABLE"); }
    }
    static Map<String, Object> map(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) result.put((String) pairs[i], pairs[i + 1]);
        return result;
    }
    static String text(JsonNode node, String name) {
        JsonNode value = node.get(name);
        if (value == null || !value.isTextual() || value.asText().isEmpty()) throw new BridgeException(400, "INVALID_FIELD", name);
        return value.asText();
    }
}
