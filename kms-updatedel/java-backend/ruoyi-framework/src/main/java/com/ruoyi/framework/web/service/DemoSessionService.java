package com.ruoyi.framework.web.service;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.common.core.domain.model.LoginUser;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

@Service
public class DemoSessionService {
    private static final String PREFIX = "kms_demo_sessions:";
    private static final long SESSION_SECONDS = 28800;
    private static final long LEASE_SECONDS = 600;
    private static final SecureRandom RANDOM = new SecureRandom();
    @Autowired private StringRedisTemplate redis;
    @Autowired private DemoIdentity projection;
    @Value("${INTERNAL_TOKEN:}") private String internalToken;
    @Value("${KMS_DEMO_NODE_LOOKUP_URL:http://dvadmin3-django:8000/internal/demo/node/}") private String nodeLookupUrl;
    private final RestTemplate http;

    public DemoSessionService() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(10000);
        http = new RestTemplate(factory);
    }

    public static String opaque() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public Map<String, Object> read(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]{43}")) throw new IllegalArgumentException("DEMO_SESSION_INVALID");
        String value = redis.opsForValue().get(PREFIX + id);
        if (value == null) throw new IllegalArgumentException("DEMO_SESSION_INVALID");
        return JSON.parseObject(value);
    }

    public void save(String id, Map<String, Object> state) {
        redis.opsForValue().set(PREFIX + id, JSON.toJSONString(state), SESSION_SECONDS, TimeUnit.SECONDS);
    }

    public Map<String, Object> initial() {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("entryMode", "DEMO");
        state.put("enabled", true);
        state.put("principalType", null);
        state.put("revision", 0L);
        state.put("csrfToken", opaque());
        return state;
    }

    public Map<String, Object> lookup(String nodeId) {
        if (nodeId == null || !nodeId.matches("[A-Za-z0-9_.-]{1,64}")) throw new IllegalArgumentException("DEMO_NODE_ID_INVALID");
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Token", internalToken);
        String url = UriComponentsBuilder.fromHttpUrl(nodeLookupUrl).queryParam("nodeId", nodeId).build().encode().toUriString();
        Map response;
        try {
            response = http.exchange(url, HttpMethod.GET, new HttpEntity<>(headers), Map.class).getBody();
        } catch (org.springframework.web.client.HttpClientErrorException.NotFound ex) {
            throw new IllegalArgumentException("DEMO_NODE_NOT_FOUND");
        } catch (org.springframework.web.client.RestClientException ex) {
            throw new IllegalArgumentException("DEMO_NODE_LOOKUP_UNAVAILABLE");
        }
        if (response == null || !Integer.valueOf(200).equals(response.get("code")) || !(response.get("data") instanceof Map)) {
            throw new IllegalArgumentException("DEMO_NODE_NOT_FOUND");
        }
        Map<String, Object> node = (Map<String, Object>) response.get("data");
        if (!nodeId.equals(node.get("nodeId"))) throw new IllegalArgumentException("DEMO_NODE_LOOKUP_INVALID");
        if (!Arrays.asList("ACTIVE", "PENDING_INIT").contains(node.get("status"))) throw new IllegalArgumentException("DEMO_NODE_DISABLED");
        if (node.get("userId") == null) throw new IllegalArgumentException("DEMO_NODE_ACCOUNT_INVALID");
        Map<String, Object> identity = new HashMap<>(node);
        identity.put("principalType", "NODE");
        projection.project(identity);
        return node;
    }

    public Map<String, Object> context(String id) {
        Map<String, Object> state = read(id);
        if ("NODE".equals(state.get("principalType"))) state.put("node", lookup(String.valueOf(state.get("nodeId"))));
        return state;
    }

    public Map<String, Object> identity(String id, Object revision, Object csrf) {
        Map<String, Object> state = context(id);
        if (revision != null && !String.valueOf(state.get("revision")).equals(String.valueOf(revision))) throw new IllegalArgumentException("DEMO_REVISION_STALE");
        if (csrf != null && !DemoBoundary.same(String.valueOf(state.get("csrfToken")), String.valueOf(csrf))) throw new IllegalArgumentException("DEMO_CSRF_INVALID");
        if (state.get("principalType") == null) throw new IllegalArgumentException("DEMO_PRINCIPAL_REQUIRED");
        Map<String, Object> identity = new LinkedHashMap<>();
        identity.put("entryMode", "DEMO");
        identity.put("principalType", state.get("principalType"));
        identity.put("sessionRevision", state.get("revision"));
        identity.put("nodeId", state.get("nodeId"));
        if ("NODE".equals(state.get("principalType"))) identity.put("userId", ((Map) state.get("node")).get("userId"));
        else identity.put("userId", -1L);
        LoginUser login = projection.project(identity);
        identity.put("userName", login.getUsername());
        identity.put("roleLevel", login.getUser().getRoleLevel());
        identity.put("ok", true);
        return identity;
    }

    public String mutex(String id) {
        read(id);
        // A timed-out lock must not let a role switch overtake a still-running mutation.
        // A crashed caller therefore fails closed for the remaining session lifetime.
        if (redis.hasKey(PREFIX + "inflight:" + id)) throw new IllegalArgumentException("DEMO_SESSION_BUSY");
        String lease = opaque();
        if (!Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(PREFIX + "lease:" + id, lease, LEASE_SECONDS, TimeUnit.SECONDS))) {
            throw new IllegalArgumentException("DEMO_SESSION_BUSY");
        }
        return lease;
    }

    public Map<String, Object> acquire(String id, Object revision, Object csrf) {
        if (revision == null || csrf == null) throw new IllegalArgumentException("DEMO_MUTATION_HEADERS_REQUIRED");
        read(id);
        String lease = mutex(id);
        try {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("ok", true);
            result.put("leaseId", lease);
            result.put("identity", identity(id, revision, csrf));
            Long pinned = redis.execute(new DefaultRedisScript<Long>(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then redis.call('set', KEYS[2], ARGV[1], 'EX', ARGV[2]); return 1 else return 0 end", Long.class),
                    Arrays.asList(PREFIX + "lease:" + id, PREFIX + "inflight:" + id), lease, String.valueOf(SESSION_SECONDS));
            if (!Long.valueOf(1L).equals(pinned)) throw new IllegalArgumentException("DEMO_LEASE_EXPIRED");
            return result;
        } catch (RuntimeException ex) {
            release(id, lease);
            throw ex;
        }
    }

    public boolean validate(String id, String lease) {
        if (id == null || lease == null) return false;
        Long value = redis.execute(new DefaultRedisScript<Long>(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end", Long.class),
                Collections.singletonList(PREFIX + "lease:" + id), lease, String.valueOf(LEASE_SECONDS));
        return Long.valueOf(1L).equals(value);
    }

    public void release(String id, String lease) {
        if (id == null || lease == null) return;
        redis.execute(new DefaultRedisScript<Long>(
                "local released = 0; for _, key in ipairs(KEYS) do if redis.call('get', key) == ARGV[1] then released = released + redis.call('del', key) end end; return released", Long.class),
                Arrays.asList(PREFIX + "lease:" + id, PREFIX + "inflight:" + id), lease);
    }

    public Map<String, Object> change(String id, String action, String nodeId, String csrf, String revision) {
        if (revision == null) throw new IllegalArgumentException("DEMO_REVISION_REQUIRED");
        String lease = mutex(id);
        try {
            Map<String, Object> state = read(id);
            if (!DemoBoundary.same(String.valueOf(state.get("csrfToken")), csrf)) throw new IllegalArgumentException("DEMO_CSRF_INVALID");
            if (revision != null && !String.valueOf(state.get("revision")).equals(revision)) throw new IllegalArgumentException("DEMO_REVISION_STALE");
            state.remove("errorCode");
            try {
                if ("entry".equals(action) || "node".equals(action)) {
                    String selected = "entry".equals(action) ? nodeId : (String) state.get("returnNodeId");
                    Map<String, Object> node = lookup(selected);
                    state.put("nodeId", selected);
                    state.put("returnNodeId", selected);
                    state.put("node", node);
                    state.put("principalType", "NODE");
                } else if ("admin".equals(action)) {
                    state.put("principalType", "ADMIN");
                    state.remove("nodeId");
                    state.remove("node");
                } else if ("logout".equals(action)) {
                    redis.delete(PREFIX + id);
                    return initial();
                } else throw new IllegalArgumentException("DEMO_ACTION_INVALID");
            } catch (IllegalArgumentException ex) {
                state.put("principalType", null);
                state.remove("nodeId");
                state.remove("node");
                state.remove("returnNodeId");
                state.put("errorCode", ex.getMessage());
            }
            state.put("revision", ((Number) state.get("revision")).longValue() + 1);
            if (!validate(id, lease)) throw new IllegalArgumentException("DEMO_LEASE_EXPIRED");
            save(id, state);
            return state;
        } finally { release(id, lease); }
    }
}
