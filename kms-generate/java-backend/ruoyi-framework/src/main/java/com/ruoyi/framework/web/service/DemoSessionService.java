package com.ruoyi.framework.web.service;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

/** Generate consumes the lifecycle authority; it never stores or signs demo sessions. */
@Service
public class DemoSessionService {
    @Value("${INTERNAL_TOKEN:}") private String internalToken;
    @Value("${KMS_DEMO_AUTHORITY_URL:http://updatedel-java:9082}") private String authorityUrl;
    private final RestTemplate http;

    public DemoSessionService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(15000);
        http = new RestTemplate(factory);
    }

    public Map<String, Object> identity(String id, Object revision, Object csrf) {
        return call("introspect", payload(id, revision, csrf));
    }

    public Map<String, Object> acquire(String id, Object revision, Object csrf) {
        return call("lease/acquire", payload(id, revision, csrf));
    }

    public boolean validate(String id, String lease) {
        Map<String, Object> payload = payload(id, null, null);
        payload.put("leaseId", lease);
        return Boolean.TRUE.equals(call("lease/validate", payload).get("ok"));
    }

    public void release(String id, String lease) {
        Map<String, Object> payload = payload(id, null, null);
        payload.put("leaseId", lease);
        call("lease/release", payload);
    }

    private Map<String, Object> payload(String id, Object revision, Object csrf) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("sessionId", id);
        if (revision != null) payload.put("revision", revision);
        if (csrf != null) payload.put("csrfToken", csrf);
        return payload;
    }

    private Map<String, Object> call(String operation, Map<String, Object> payload) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Token", internalToken);
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map response;
        try {
            response = http.exchange(authorityUrl + "/internal/lifecycle/demo/" + operation, HttpMethod.POST,
                    new HttpEntity<>(payload, headers), Map.class).getBody();
        } catch (org.springframework.web.client.RestClientException ex) {
            throw new IllegalArgumentException("DEMO_AUTHORITY_UNAVAILABLE");
        }
        Map<String, Object> result = response != null && response.get("data") instanceof Map ? (Map<String, Object>) response.get("data") : null;
        if (result == null || !Boolean.TRUE.equals(result.get("ok"))) {
            throw new IllegalArgumentException(result == null ? "DEMO_AUTHORITY_INVALID" : String.valueOf(result.get("errorCode")));
        }
        return result;
    }
}
