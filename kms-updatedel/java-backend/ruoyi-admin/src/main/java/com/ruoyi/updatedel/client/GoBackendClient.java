package com.ruoyi.updatedel.client;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.updatedel.domain.Keymanage;
import java.util.HashMap;
import java.util.Map;
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

@Component
public class GoBackendClient {
    private static final Logger log = LoggerFactory.getLogger(GoBackendClient.class);
    private static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";

    /**
     * 已认证身份头：由本客户端写入，Go 侧据此确定密钥归属。
     * Go 端不再信任请求体中的 user 字段，避免伪造任意身份触达更新/回收。
     */
    private static final String VERIFIED_USER_HEADER = "X-Kms-User";

    @Value("${kms.go-backend.url:http://updatedel-go:8082}")
    private String goBackendUrl;

    @Value("${kms.go-backend.internal-token}")
    private String internalToken;

    private final RestTemplate restTemplate = new RestTemplate();

    public void updateKey(Keymanage keymanage) {
        Map<String, Object> body = new HashMap<>();
        body.put("keyId", keymanage.getKeyId());
        body.put("user", keymanage.getUserName());
        body.put("ua", keymanage.getUa());
        body.put("encrytType", keymanage.getEncrytType());
        body.put("encrytName", keymanage.getEncrytName());
        body.put("keyName", keymanage.getKeyName());
        body.put("keyUse", keymanage.getKeyUse());
        body.put("autoUpdate", keymanage.getAutoUpdate());
        body.put("keyDomain", keymanage.getKeyDomain());
        callGoApi("/lifecycle/request/UPDATE_KEY", body, keymanage.getUserName());
    }

    public void revokeKey(Long keyId, String userName) {
        Map<String, Object> body = new HashMap<>();
        body.put("keyId", keyId);
        body.put("user", userName);
        callGoApi("/lifecycle/request/REVOKE_KEY", body, userName);
    }

    private void callGoApi(String path, Map<String, Object> body, String verifiedUserName) {
        String url = goBackendUrl + path;
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set(INTERNAL_TOKEN_HEADER, internalToken);

            String actingUser = resolveVerifiedUser(verifiedUserName);
            if (actingUser != null && !actingUser.isEmpty()) {
                headers.set(VERIFIED_USER_HEADER, actingUser);
            }

            HttpEntity<String> request = new HttpEntity<>(JSON.toJSONString(body), headers);

            ResponseEntity<String> response = restTemplate.postForEntity(url, request, String.class);
            if (!response.getStatusCode().is2xxSuccessful()) {
                throw new RuntimeException("Go 服务返回错误 [" + response.getStatusCodeValue() + "]: " + response.getBody());
            }

            JSONObject payload = JSON.parseObject(response.getBody());
            if (payload.getIntValue("code") != 200) {
                throw new RuntimeException("Go 服务业务错误: " + payload.getString("msg"));
            }
        } catch (RestClientException e) {
            log.error("Lifecycle Go 服务网络异常: path={}, error={}", path, e.getMessage(), e);
            throw new RuntimeException("无法连接 Go 生命周期服务: " + e.getMessage(), e);
        }
    }

    /**
     * 解析本次调用应携带的已认证身份。
     * <p>
     * 优先使用业务层显式校验过归属的用户名（即目标密钥的所有者）；
     * 否则回退到当前登录会话用户。会话不可用时返回 null，
     * 调用方不写该头，Go 端将拒绝受理。
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
