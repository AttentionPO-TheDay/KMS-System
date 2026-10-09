package com.ruoyi.framework.web.service;

import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class DemoSessionServiceTest {
    private DemoSessionService sessions;
    private Map<String, String> store;
    private String id;
    private String csrf;

    @BeforeEach
    @SuppressWarnings("unchecked")
    public void setup() {
        sessions = new DemoSessionService();
        ReflectionTestUtils.setField(sessions, "internalToken", "test-only-secret");
        ReflectionTestUtils.setField(sessions, "nodeLookupUrl", "http://nodes.invalid/internal/demo/node/");
        store = new HashMap<>();
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> values = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);
        when(values.get(anyString())).thenAnswer(i -> store.get(i.getArgument(0)));
        doAnswer(i -> { store.put(i.getArgument(0), i.getArgument(1)); return null; })
                .when(values).set(anyString(), anyString(), anyLong(), any(TimeUnit.class));
        when(values.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class))).thenAnswer(i -> {
            String key = i.getArgument(0);
            if (store.containsKey(key)) return false;
            store.put(key, i.getArgument(1));
            return true;
        });
        when(redis.delete(anyString())).thenAnswer(i -> store.remove(i.getArgument(0)) != null);
        when(redis.hasKey(anyString())).thenAnswer(i -> store.containsKey(i.getArgument(0)));
        org.mockito.stubbing.Answer<Long> scriptAnswer = i -> {
            RedisScript<?> script = i.getArgument(0);
            List<String> keys = i.getArgument(1);
            String key = keys.get(0);
            String lease = i.getArgument(2);
            if (script.getScriptAsString().contains("'del'")) {
                long released = 0;
                for (String item : keys) if (lease.equals(store.get(item))) {
                    store.remove(item);
                    released++;
                }
                return released;
            }
            if (!lease.equals(store.get(key))) return 0L;
            if (script.getScriptAsString().contains("'set'")) store.put(keys.get(1), lease);
            return 1L;
        };
        when(redis.execute(any(RedisScript.class), anyList(), anyString())).thenAnswer(scriptAnswer);
        when(redis.execute(any(RedisScript.class), anyList(), anyString(), anyString())).thenAnswer(scriptAnswer);
        ReflectionTestUtils.setField(sessions, "redis", redis);
        DemoIdentity projection = mock(DemoIdentity.class);
        SysUser admin = new SysUser();
        admin.setUserId(-1L);
        admin.setUserName("DEMO_ADMIN");
        admin.setRoleLevel(0);
        when(projection.project(anyMap())).thenReturn(new LoginUser(-1L, null, admin, Collections.emptySet()));
        ReflectionTestUtils.setField(sessions, "projection", projection);
        id = DemoSessionService.opaque();
        Map<String, Object> initial = sessions.initial();
        csrf = (String) initial.get("csrfToken");
        sessions.save(id, initial);
        sessions.change(id, "admin", null, csrf, "0");
    }

    @Test
    public void administratorIsSyntheticAndRevisionBound() {
        Map<String, Object> identity = sessions.identity(id, "1", null);
        assertEquals(-1L, identity.get("userId"));
        assertEquals("DEMO_ADMIN", identity.get("userName"));
        assertNull(identity.get("nodeId"));
        denied("DEMO_REVISION_STALE", () -> sessions.identity(id, "0", null));
    }

    @Test
    public void mutationsRequireRevisionCsrfAndHoldRoleSwitchMutex() {
        denied("DEMO_MUTATION_HEADERS_REQUIRED", () -> sessions.acquire(id, null, csrf));
        denied("DEMO_CSRF_INVALID", () -> sessions.acquire(id, "1", "wrong"));
        Map<String, Object> lease = sessions.acquire(id, "1", csrf);
        String leaseId = (String) lease.get("leaseId");
        assertTrue(sessions.validate(id, leaseId));
        denied("DEMO_SESSION_BUSY", () -> sessions.change(id, "admin", null, csrf, "1"));
        sessions.release(id, "wrong-owner");
        assertTrue(sessions.validate(id, leaseId));
        sessions.release(id, leaseId);
        assertFalse(sessions.validate(id, leaseId));
        sessions.change(id, "admin", null, csrf, "1");
        denied("DEMO_REVISION_STALE", () -> sessions.acquire(id, "1", csrf));
    }

    @Test
    public void expiredLeaseDoesNotAllowRoleSwitchToOvertakeMutation() {
        Map<String, Object> lease = sessions.acquire(id, "1", csrf);
        store.remove("kms_demo_sessions:lease:" + id);
        denied("DEMO_SESSION_BUSY", () -> sessions.change(id, "admin", null, csrf, "1"));
        sessions.release(id, (String) lease.get("leaseId"));
        assertEquals("ADMIN", sessions.change(id, "admin", null, csrf, "1").get("principalType"));
    }

    @Test
    public void contextChangesRequireRevision() {
        denied("DEMO_REVISION_REQUIRED", () -> sessions.change(id, "admin", null, csrf, null));
        denied("DEMO_REVISION_STALE", () -> sessions.change(id, "admin", null, csrf, "0"));
    }

    @Test
    public void invalidEntryClearsCurrentAdministratorRatherThanKeepingPrivileges() {
        Map<String, Object> context = sessions.change(id, "entry", "bad/node", csrf, "1");
        assertEquals("DEMO_NODE_ID_INVALID", context.get("errorCode"));
        assertNull(context.get("principalType"));
        assertFalse(context.containsKey("returnNodeId"));
        denied("DEMO_PRINCIPAL_REQUIRED", () -> sessions.identity(id, "2", null));
        assertEquals("ADMIN", sessions.change(id, "admin", null, csrf, "2").get("principalType"));
    }

    @Test
    public void nodeEntryAndContextQueryFreshAuthoritativeNodeStatus() {
        org.springframework.test.web.client.MockRestServiceServer nodes = org.springframework.test.web.client.MockRestServiceServer.createServer(
                (org.springframework.web.client.RestTemplate) ReflectionTestUtils.getField(sessions, "http"));
        String url = "http://nodes.invalid/internal/demo/node/?nodeId=node-A";
        nodes.expect(org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo(url))
                .andExpect(org.springframework.test.web.client.match.MockRestRequestMatchers.method(org.springframework.http.HttpMethod.GET))
                .andExpect(org.springframework.test.web.client.match.MockRestRequestMatchers.header("X-Internal-Token", "test-only-secret"))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess(
                        "{\"code\":200,\"data\":{\"nodeId\":\"node-A\",\"userId\":12,\"status\":\"PENDING_INIT\"}}", org.springframework.http.MediaType.APPLICATION_JSON));
        nodes.expect(org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo(url))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess(
                        "{\"code\":200,\"data\":{\"nodeId\":\"node-A\",\"userId\":12,\"status\":\"ACTIVE\"}}", org.springframework.http.MediaType.APPLICATION_JSON));
        nodes.expect(org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo(url))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess(
                        "{\"code\":200,\"data\":{\"nodeId\":\"node-A\",\"userId\":12,\"status\":\"DISABLED\"}}", org.springframework.http.MediaType.APPLICATION_JSON));
        assertEquals("NODE", sessions.change(id, "entry", "node-A", csrf, "1").get("principalType"));
        assertEquals("ACTIVE", ((Map) sessions.context(id).get("node")).get("status"));
        denied("DEMO_NODE_DISABLED", () -> sessions.identity(id, "2", null));
        nodes.verify();
    }

    @Test
    public void nonexistentNodeIsRejectedWithoutProvisioningOrRetainingAdministrator() {
        org.springframework.test.web.client.MockRestServiceServer nodes = org.springframework.test.web.client.MockRestServiceServer.createServer(
                (org.springframework.web.client.RestTemplate) ReflectionTestUtils.getField(sessions, "http"));
        nodes.expect(org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo("http://nodes.invalid/internal/demo/node/?nodeId=missing"))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators.withStatus(org.springframework.http.HttpStatus.NOT_FOUND));
        Map<String, Object> context = sessions.change(id, "entry", "missing", csrf, "1");
        assertEquals("DEMO_NODE_NOT_FOUND", context.get("errorCode"));
        assertNull(context.get("principalType"));
        nodes.verify();
    }

    @Test
    public void logoutInvalidatesOpaqueSession() {
        sessions.change(id, "logout", null, csrf, "1");
        denied("DEMO_SESSION_INVALID", () -> sessions.read(id));
    }

    private void denied(String code, Runnable action) {
        try { action.run(); fail("Expected " + code); }
        catch (IllegalArgumentException ex) { assertEquals(code, ex.getMessage()); }
    }
}
