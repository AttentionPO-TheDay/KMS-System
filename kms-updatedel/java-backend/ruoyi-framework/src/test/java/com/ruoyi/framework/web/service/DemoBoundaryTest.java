package com.ruoyi.framework.web.service;

import javax.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;

public class DemoBoundaryTest {
    private DemoBoundary boundary;
    private MockHttpServletRequest request;

    @BeforeEach
    public void setup() {
        boundary = new DemoBoundary();
        ReflectionTestUtils.setField(boundary, "enabled", true);
        ReflectionTestUtils.setField(boundary, "internalToken", "test-only-secret");
        ReflectionTestUtils.setField(boundary, "hosts", "127.0.0.1:8088,localhost:8088");
        ReflectionTestUtils.setField(boundary, "origins", "http://127.0.0.1:8088,http://localhost:8088");
        request = new MockHttpServletRequest();
        request.addHeader("Host", "127.0.0.1:8088");
        request.addHeader("X-Kms-Entry-Mode", "demo");
        request.addHeader("X-Kms-Demo-Gateway", "test-only-secret");
    }

    @Test
    public void validGatewayAndExplicitOriginAccepted() {
        boundary.requireGateway(request);
        request.addHeader("Origin", "http://localhost:8088");
        boundary.requireOrigin(request);
        boundary.requireGateway(request);
    }

    @Test
    public void disabledWrongHostForgedGatewayAndOldEntryRejected() {
        ReflectionTestUtils.setField(boundary, "enabled", false);
        denied(() -> boundary.requireGateway(request));
        ReflectionTestUtils.setField(boundary, "enabled", true);
        request.removeHeader("Host");
        request.addHeader("Host", "localhost");
        denied(() -> boundary.requireGateway(request));
        request.removeHeader("Host");
        request.addHeader("Host", "localhost:8088");
        request.removeHeader("X-Kms-Demo-Gateway");
        request.addHeader("X-Kms-Demo-Gateway", "forged");
        denied(() -> boundary.requireGateway(request));
        request.removeHeader("X-Kms-Entry-Mode");
        assertFalse(boundary.isDemo(request));
        denied(() -> boundary.requireGateway(request));
    }

    @Test
    public void missingForeignAndNullOriginsRejected() {
        denied(() -> boundary.requireOrigin(request));
        request.addHeader("Origin", "http://attacker.invalid");
        denied(() -> boundary.requireGateway(request));
        request.removeHeader("Origin");
        request.addHeader("Origin", "null");
        denied(() -> boundary.requireOrigin(request));
    }

    @Test
    public void onlyOpaqueDemoCookieIsRead() {
        request.setCookies(new Cookie("Admin-Token", "legacy-jwt"), new Cookie(DemoBoundary.COOKIE, "ADMIN"));
        assertNull(boundary.sessionId(request));
        String id = DemoSessionService.opaque();
        assertEquals(43, id.length());
        request.setCookies(new Cookie(DemoBoundary.COOKIE, id));
        assertEquals(id, boundary.sessionId(request));
    }

    @Test
    public void demoCapabilitiesDoNotGrantGenericSystemAdministrationOrAdminKeyGeneration() {
        DemoIdentity identity = new DemoIdentity();
        java.util.Map<String, Object> admin = java.util.Collections.singletonMap("principalType", "ADMIN");
        java.util.Map<String, Object> node = java.util.Collections.singletonMap("principalType", "NODE");
        request.setServletPath("/system/user");
        request.setMethod("POST");
        assertFalse(identity.allowed(request, admin));
        request.setServletPath("/generate/keymanage");
        assertFalse(identity.allowed(request, admin));
        assertTrue(identity.allowed(request, node));
        request.setServletPath("/generate/user/register");
        assertFalse(identity.allowed(request, node));
        request.setServletPath("/monitor/operlog/list");
        request.setMethod("GET");
        assertTrue(identity.allowed(request, admin));
        assertFalse(identity.allowed(request, node));
        request.setServletPath("/internal/lifecycle/session/issue");
        assertFalse(identity.allowed(request, admin));
    }

    private void denied(Runnable action) {
        try { action.run(); fail("Expected boundary rejection"); }
        catch (IllegalArgumentException expected) { }
    }
}
