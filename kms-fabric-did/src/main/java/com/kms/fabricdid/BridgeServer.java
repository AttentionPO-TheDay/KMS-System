package com.kms.fabricdid;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class BridgeServer {
    private final HttpServer server;
    private final ThreadPoolExecutor executor;
    private final BindingService service;
    private static final String BASE = "/internal/fabric-did/";
    BridgeServer(BridgeConfig config, DidSdk.Factory factory) throws Exception {
        service = new BindingService(config, factory);
        server = HttpServer.create(new InetSocketAddress(config.host, config.port), 32);
        executor = new ThreadPoolExecutor(2, 8, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<Runnable>(32), new ThreadPoolExecutor.AbortPolicy());
        server.setExecutor(executor);
        server.createContext("/", this::handle);
    }
    void start() { server.start(); }
    int port() { return server.getAddress().getPort(); }
    void stop() { server.stop(0); executor.shutdownNow(); }
    private void handle(HttpExchange exchange) {
        try {
            String path = exchange.getRequestURI().getPath();
            if ("/health".equals(path) && "GET".equals(exchange.getRequestMethod())) {
                reply(exchange, 200, Json.map("code", 200, "msg", "ok", "data", Json.map("status", service.config.status(), "provider", "FABRIC_DID",
                        "chainWriteState", service.config.chainWriteState(), "writeEnabled", service.config.effectiveWriteEnabled()))); return;
            }
            String token = exchange.getRequestHeaders().getFirst("X-Internal-Token");
            // 未设置服务端凭据时 fail closed，绝不让空字符串变成合法认证。
            if (service.config.internalToken.isEmpty() || token == null || !MessageDigest.isEqual(
                    token.getBytes(StandardCharsets.UTF_8), service.config.internalToken.getBytes(StandardCharsets.UTF_8)))
                throw new BridgeException(401, "UNAUTHORIZED");
            if (!path.startsWith(BASE)) throw new BridgeException(404, "NOT_FOUND");
            String action = path.substring(BASE.length());
            String method = exchange.getRequestMethod();
            Map<String, Object> result;
            if ("status".equals(action) && "GET".equals(method)) result = service.status();
            else if ("did".equals(action) && "GET".equals(method)) result = service.read(queryDid(exchange));
            else if ("POST".equals(method)) {
                JsonNode body = body(exchange);
                if ("bindings/prepare".equals(action)) result = service.prepare(body);
                else if ("bindings/submit".equals(action)) result = service.submit(body);
                else if ("bindings/verify".equals(action)) result = service.verify(body);
                else throw new BridgeException(404, "NOT_FOUND");
            } else throw new BridgeException(405, "METHOD_NOT_ALLOWED");
            reply(exchange, 200, Json.map("code", 200, "msg", "ok", "data", result));
        } catch (BridgeException e) {
            reply(exchange, e.httpStatus, Json.map("code", e.httpStatus, "msg", e.getMessage(), "data", Json.map("errorCode", e.errorCode)));
        } catch (Exception | LinkageError e) {
            // 异常可能带证书/私钥路径；对外只输出稳定错误码，不记录原始 SDK 异常。
            reply(exchange, 502, Json.map("code", 502, "msg", "SDK_OPERATION_FAILED", "data", Json.map("errorCode", "SDK_OPERATION_FAILED")));
        } finally { exchange.close(); }
    }
    private static JsonNode body(HttpExchange exchange) {
        try (InputStream input = exchange.getRequestBody(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] chunk = new byte[4096];
            int size;
            while ((size = input.read(chunk)) >= 0) {
                if (bytes.size() + size > 131072) throw new BridgeException(413, "REQUEST_TOO_LARGE");
                bytes.write(chunk, 0, size);
            }
            return Json.MAPPER.readTree(bytes.toByteArray());
        } catch (BridgeException e) { throw e; }
        catch (Exception e) { throw new BridgeException(400, "INVALID_JSON"); }
    }
    private static String queryDid(HttpExchange exchange) throws Exception {
        String query = exchange.getRequestURI().getRawQuery();
        if (query == null) throw new BridgeException(400, "MISSING_DID");
        String did = null;
        for (String pair : query.split("&")) {
            String[] parts = pair.split("=", 2);
            if (parts.length == 2 && "did".equals(URLDecoder.decode(parts[0], "UTF-8"))) {
                if (did != null) throw new BridgeException(400, "DUPLICATE_DID");
                did = URLDecoder.decode(parts[1], "UTF-8");
            }
        }
        if (did == null) throw new BridgeException(400, "MISSING_DID");
        return did;
    }
    private static void reply(HttpExchange exchange, int status, Object body) {
        try {
            byte[] bytes = Json.encode(body).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        } catch (Exception ignored) { /* 连接断开不会改变已保存的交易计划。 */ }
    }
    public static void main(String[] args) throws Exception {
        BridgeConfig config = new BridgeConfig(System.getenv());
        BridgeServer app = new BridgeServer(config, () -> new VendorDidSdk(config));
        app.start();
        Runtime.getRuntime().addShutdownHook(new Thread(app::stop));
        System.out.println("Fabric DID Bridge started; status=" + config.status() + "; port=" + app.port());
    }
}
