package com.ruoyi.generate.client;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.Keymanage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.Map;

/**
 * Go 高性能生成服务客户端
 * <p>
 * 调用流程：
 * 1. Java（已完成 Session 鉴权）→ 携带 X-Internal-Token 转发 → Go
 * 2. Go 验证 Token 放行（无需用户密码）→ 执行密码学计算 → 发送 Kafka
 * 3. Java Kafka 消费者（GenerateKafkaConsumer）统一落库
 * 4. Java 仅返回本次生成结果快照给前端展示
 */
@Component
public class GoBackendClient {

    private static final Logger log = LoggerFactory.getLogger(GoBackendClient.class);

    private static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";

    /**
     * 已认证身份头：由本客户端写入，Go 侧据此确定密钥归属。
     * Go 端不再信任请求体中的 user 字段，避免伪造任意身份的生成请求。
     */
    private static final String VERIFIED_USER_HEADER = "X-Kms-User";

    @Value("${kms.go-backend.url:http://localhost:8081}")
    private String goBackendUrl;

    // 内部 Token 必须由环境变量 INTERNAL_TOKEN 注入，无默认值（历史默认值为公开值）。
    @Value("${kms.go-backend.internal-token}")
    private String internalToken;

    private final RestTemplate restTemplate = new RestTemplate();

    /**
     * 调用 Go 服务执行 ENROLL_KEY（密钥生成）
     *
     * @param keymanage 密钥信息（含 userName, encrytType, encrytName, uA, keyDomain 等）
     * @return Go 计算生成的 keyValue 字符串（SM2/SSCL 为 JSON 串）
     * @throws RuntimeException 调用失败时抛出
     */
    public String enrollKey(Keymanage keymanage) {
        return enrollKey(keymanage, null);
    }

    /**
     * 调用 Go 服务执行 ENROLL_KEY（密钥生成）
     *
     * @param keymanage       密钥信息（含 userName, encrytType, encrytName, uA, keyDomain 等）
     * @param verifiedUserName 已由业务层校验归属的用户名；为 null 时取当前登录会话用户
     * @return Go 计算生成的 keyValue 字符串（SM2/SSCL 为 JSON 串）
     * @throws RuntimeException 调用失败时抛出
     */
    public String enrollKey(Keymanage keymanage, String verifiedUserName) {
        Map<String, Object> body = new HashMap<>();
        body.put("user", keymanage.getUserName());
        body.put("encryt_type", keymanage.getEncrytType());
        body.put("encryt_name", keymanage.getEncrytName());
        body.put("ua", keymanage.getuA() != null ? keymanage.getuA() : "");
        body.put("key_domain", keymanage.getKeyDomain() != null ? keymanage.getKeyDomain() : "");
        body.put("key_name", keymanage.getKeyName() != null ? keymanage.getKeyName() : "example");
        body.put("key_use", keymanage.getKeyUse() != null ? keymanage.getKeyUse() : "加解密");
        body.put("auto_update", keymanage.getAutoUpdate() != null ? keymanage.getAutoUpdate() : "false");
        if (isPqAlgorithm(keymanage.getEncrytName())) {
            body.put("pq_mode", "demo_generated");
        }

        return callGoApi("/generate/request/ENROLL_KEY", body, verifiedUserName);
    }

    public String reenrollKey(Keymanage keymanage) {
        return reenrollKey(keymanage, null);
    }

    public String reenrollKey(Keymanage keymanage, String verifiedUserName) {
        Map<String, Object> body = new HashMap<>();
        body.put("user", keymanage.getUserName());
        body.put("encryt_type", keymanage.getEncrytType());
        body.put("encryt_name", keymanage.getEncrytName());
        body.put("ua", keymanage.getuA() != null ? keymanage.getuA() : "");
        body.put("key_domain", keymanage.getKeyDomain() != null ? keymanage.getKeyDomain() : "");
        body.put("key_name", keymanage.getKeyName() != null ? keymanage.getKeyName() : "example");
        body.put("key_use", keymanage.getKeyUse() != null ? keymanage.getKeyUse() : "加解密");
        body.put("auto_update", keymanage.getAutoUpdate() != null ? keymanage.getAutoUpdate() : "false");
        if (isPqAlgorithm(keymanage.getEncrytName())) {
            body.put("pq_mode", "demo_generated");
        }

        return callGoApi("/generate/request/REENROLL_KEY", body, verifiedUserName);
    }

    /**
     * 调用 Go 服务获取公共参数（SSCL 多项式系数等）
     *
     * @param encrytType 加密类型
     * @param encrytName 加密算法名称
     * @return Go 返回的公共参数 JSON 字符串
     */
    public String getComParam(String encrytType, String encrytName) {
        Map<String, Object> body = new HashMap<>();
        body.put("encryt_type", encrytType);
        body.put("encryt_name", encrytName);
        return callGoApi("/generate/request/comparam", body, null);
    }

    private boolean isPqAlgorithm(String algorithm) {
        if (algorithm == null) {
            return false;
        }
        String normalized = algorithm.toUpperCase();
        return normalized.contains("KYBER") || normalized.contains("FALCON") || normalized.contains("ML-KEM") || normalized.startsWith("PQ_");
    }

    /**
     * 通用 Go API 调用方法
     *
     * @param path             接口路径（如 /generate/request/ENROLL_KEY）
     * @param body             请求体
     * @param verifiedUserName 显式指定的已认证用户名；为 null 时取当前登录会话用户
     * @return 响应中 data 字段的 JSON 字符串，若无 data 则返回 code=200 时的空串
     */
    private String callGoApi(String path, Map<String, Object> body, String verifiedUserName) {
        String url = goBackendUrl + path;
        String bodyJson = JSON.toJSONString(body);

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set(INTERNAL_TOKEN_HEADER, internalToken);

            String actingUser = resolveVerifiedUser(verifiedUserName);
            if (actingUser != null && !actingUser.isEmpty()) {
                headers.set(VERIFIED_USER_HEADER, actingUser);
            }

            HttpEntity<String> request = new HttpEntity<>(bodyJson, headers);

            ResponseEntity<String> response = restTemplate.postForEntity(url, request, String.class);

            if (!response.getStatusCode().is2xxSuccessful()) {
                log.error("Go 服务调用失败: path={}, status={}, body={}", path, response.getStatusCodeValue(), response.getBody());
                throw new RuntimeException("Go 服务返回错误 [" + response.getStatusCodeValue() + "]: " + response.getBody());
            }

            JSONObject resp = JSON.parseObject(response.getBody());
            int code = resp.getIntValue("code");
            if (code != 200) {
                String msg = resp.getString("msg");
                log.error("Go 服务业务错误: path={}, code={}, msg={}", path, code, msg);
                throw new RuntimeException("Go 服务业务错误: " + msg);
            }

            // data 可能是字符串或对象，统一转为字符串返回
            Object data = resp.get("data");
            if (data == null) {
                return "";
            }
            return data instanceof String ? (String) data : JSON.toJSONString(data);

        } catch (RestClientException e) {
            log.error("Go 服务网络异常: path={}, error={}", path, e.getMessage(), e);
            throw new RuntimeException("无法连接 Go 生成服务: " + e.getMessage(), e);
        }
    }

    /**
     * 解析本次调用应携带的已认证身份。
     * <p>
     * 优先使用业务层显式校验过归属的用户名；否则回退到当前登录会话用户。
     * 会话不可用时返回 null（调用方不会写该头，Go 端将拒绝受理）。
     */
    private String resolveVerifiedUser(String explicitUser) {
        if (explicitUser != null && !explicitUser.trim().isEmpty()) {
            return explicitUser.trim();
        }
        try {
            String sessionUser = SecurityUtils.getUsername();
            return sessionUser == null || sessionUser.trim().isEmpty() ? null : sessionUser.trim();
        } catch (Exception e) {
            log.warn("无法从当前会话解析用户名，将不携带 {} 头: {}", VERIFIED_USER_HEADER, e.getMessage());
            return null;
        }
    }
}
