package com.kms.fabricdid;

import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** 受限诊断文件；不读取身份配置，不收集 gRPC trailers，不回传给 HTTP。 */
final class SdkDiagnostics {
    private static final Pattern PEM = Pattern.compile("(?s)-----BEGIN ([A-Z0-9 ]+)-----.*?-----END \\1-----");
    private static final Pattern AUTHORIZATION = Pattern.compile("(?i)(authorization\\s*[:=]\\s*)(?:Bearer\\s+|Basic\\s+)?[^\\s,;}]+");
    private static final Pattern SECRET = Pattern.compile(
            "(?i)([\\\"']?(?:private[_-]?key|secret|password|authorization|(?:[a-z0-9]+[_-])*token|casToken)[\\\"']?\\s*[:=]\\s*)(?:\\\"[^\\\"]*\\\"|'[^']*'|[^\\s,;}&]+)");
    private SdkDiagnostics() { }

    static String safeText(String value) {
        if (value == null) return null;
        String text = PEM.matcher(value).replaceAll("[REDACTED PEM]");
        text = AUTHORIZATION.matcher(text).replaceAll("$1[REDACTED]");
        text = SECRET.matcher(text).replaceAll("$1[REDACTED]");
        for (Map.Entry<String, String> variable : System.getenv().entrySet()) {
            String name = variable.getKey().toUpperCase(java.util.Locale.ROOT), secret = variable.getValue();
            if (!secret.isEmpty() && (name.contains("TOKEN") || name.contains("PASSWORD") || name.contains("SECRET")))
                text = text.replace(secret, "[REDACTED]");
        }
        // 对实际多行和 JSON 中转义的 PEM 同样脱敏。
        if (text.contains("-----BEGIN")) text = "[REDACTED INCOMPLETE PEM]";
        return text.length() > 2048 ? text.substring(0, 2048) + " [truncated]" : text;
    }

    static List<Object> describe(Throwable error) {
        List<Object> result = new ArrayList<>();
        Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<Throwable, Boolean>());
        collect(error, "root", null, result, seen);
        return result;
    }

    private static void collect(Throwable error, String relation, Integer parent, List<Object> result, Set<Throwable> seen) {
        if (error == null || result.size() >= 16 || !seen.add(error)) return;
        int index = result.size();
        Map<String, Object> item = Json.map("type", error.getClass().getName(), "message", safeText(error.getMessage()),
                "relation", relation, "parent", parent);
        List<String> stack = new ArrayList<>();
        StackTraceElement[] frames = error.getStackTrace();
        for (int i = 0; i < frames.length && i < 12; i++) stack.add(safeText(frames[i].toString()));
        item.put("stack", stack);
        if (error instanceof StatusRuntimeException)
            item.put("grpcStatus", ((StatusRuntimeException) error).getStatus().getCode().name());
        if (error instanceof StatusException)
            item.put("grpcStatus", ((StatusException) error).getStatus().getCode().name());
        if (error instanceof com.yunphant.yunid.sdk.exception.DidSdkException) {
            com.yunphant.yunid.sdk.exception.DidSdkException sdk = (com.yunphant.yunid.sdk.exception.DidSdkException) error;
            item.put("sdkErrorCode", sdk.getErrorCode());
            item.put("sdkErrorMsg", safeText(sdk.getErrorMsg()));
        }
        result.add(item);
        collect(error.getCause(), "cause", index, result, seen);
        for (Throwable suppressed : error.getSuppressed()) collect(suppressed, "suppressed", index, result, seen);
    }

    static synchronized void record(Path path, Throwable error) throws java.io.IOException {
        SysPidService.secureDirectory(path.getParent());
        com.fasterxml.jackson.databind.node.ArrayNode events = Json.MAPPER.createArrayNode();
        if (Files.isRegularFile(path)) {
            com.fasterxml.jackson.databind.JsonNode previous = Json.MAPPER.readTree(Files.readAllBytes(path)).get("events");
            if (previous != null && previous.isArray()) events.addAll((com.fasterxml.jackson.databind.node.ArrayNode) previous);
        }
        while (events.size() >= 16) events.remove(0);
        events.add(Json.MAPPER.valueToTree(Json.map("time", Instant.now().toString(), "exceptions", describe(error))));
        SysPidService.save(path, Json.encode(Json.map("schemaVersion", 1, "events", events)));
    }
}
