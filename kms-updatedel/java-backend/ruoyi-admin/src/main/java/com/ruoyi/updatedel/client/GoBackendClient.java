package com.ruoyi.updatedel.client;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
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

    @Value("${kms.go-backend.url:http://updatedel-go:8082}")
    private String goBackendUrl;

    @Value("${kms.go-backend.internal-token:kms-generate-internal-secret-2026}")
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
        callGoApi("/lifecycle/request/UPDATE_KEY", body);
    }

    public void revokeKey(Long keyId, String userName) {
        Map<String, Object> body = new HashMap<>();
        body.put("keyId", keyId);
        body.put("user", userName);
        callGoApi("/lifecycle/request/REVOKE_KEY", body);
    }

    private void callGoApi(String path, Map<String, Object> body) {
        String url = goBackendUrl + path;
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set(INTERNAL_TOKEN_HEADER, internalToken);
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
}
