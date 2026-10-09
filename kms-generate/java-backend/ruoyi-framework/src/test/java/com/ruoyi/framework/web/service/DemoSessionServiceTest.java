package com.ruoyi.framework.web.service;

import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

public class DemoSessionServiceTest {
    private DemoSessionService adapter;
    private MockRestServiceServer authority;

    @BeforeEach
    public void setup() {
        adapter = new DemoSessionService();
        ReflectionTestUtils.setField(adapter, "internalToken", "test-only-secret");
        ReflectionTestUtils.setField(adapter, "authorityUrl", "http://authority.invalid:9082");
        authority = MockRestServiceServer.createServer((RestTemplate) ReflectionTestUtils.getField(adapter, "http"));
    }

    @Test
    public void consumesSyntheticIdentityFromSingleAuthority() {
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/introspect"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Internal-Token", "test-only-secret"))
                .andExpect(content().json("{\"sessionId\":\"opaque-session\",\"revision\":7}"))
                .andRespond(withSuccess("{\"code\":200,\"data\":{\"ok\":true,\"entryMode\":\"DEMO\",\"principalType\":\"ADMIN\",\"userId\":-1,\"userName\":\"DEMO_ADMIN\",\"sessionRevision\":7}}", MediaType.APPLICATION_JSON));
        Map<String, Object> identity = adapter.identity("opaque-session", 7, null);
        assertEquals("DEMO_ADMIN", identity.get("userName"));
        assertEquals(-1, identity.get("userId"));
        authority.verify();
    }

    @Test
    public void acquireValidateReleaseUseSameAuthorityAndLeaseOwner() {
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/lease/acquire"))
                .andExpect(content().json("{\"sessionId\":\"session\",\"revision\":3,\"csrfToken\":\"csrf\"}"))
                .andRespond(withSuccess("{\"code\":200,\"data\":{\"ok\":true,\"leaseId\":\"owner\",\"identity\":{\"principalType\":\"NODE\"}}}", MediaType.APPLICATION_JSON));
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/lease/validate"))
                .andExpect(content().json("{\"sessionId\":\"session\",\"leaseId\":\"owner\"}"))
                .andRespond(withSuccess("{\"code\":200,\"data\":{\"ok\":true}}", MediaType.APPLICATION_JSON));
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/lease/release"))
                .andExpect(header("X-Internal-Token", "test-only-secret"))
                .andExpect(content().json("{\"sessionId\":\"session\",\"leaseId\":\"owner\"}"))
                .andRespond(withSuccess("{\"code\":200,\"data\":{\"ok\":true}}", MediaType.APPLICATION_JSON));
        assertEquals("owner", adapter.acquire("session", 3, "csrf").get("leaseId"));
        assertTrue(adapter.validate("session", "owner"));
        adapter.release("session", "owner");
        authority.verify();
    }

    @Test
    public void staleRevisionAndAuthorityOutageDoNotFallbackToLegacyToken() {
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/introspect"))
                .andRespond(withSuccess("{\"code\":200,\"data\":{\"ok\":false,\"errorCode\":\"DEMO_REVISION_STALE\"}}", MediaType.APPLICATION_JSON));
        try { adapter.identity("session", 2, null); fail("Expected stale revision rejection"); }
        catch (IllegalArgumentException ex) { assertEquals("DEMO_REVISION_STALE", ex.getMessage()); }
        authority.verify();
        authority.reset();
        authority.expect(requestTo("http://authority.invalid:9082/internal/lifecycle/demo/introspect"))
                .andRespond(withServerError());
        try { adapter.identity("session", 2, null); fail("Expected fail closed"); }
        catch (IllegalArgumentException ex) { assertEquals("DEMO_AUTHORITY_UNAVAILABLE", ex.getMessage()); }
        authority.verify();
    }
}
