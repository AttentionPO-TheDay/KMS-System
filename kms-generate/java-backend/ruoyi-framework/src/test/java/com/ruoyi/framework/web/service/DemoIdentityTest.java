package com.ruoyi.framework.web.service;

import com.ruoyi.framework.security.filter.JwtAuthenticationTokenFilter;
import com.ruoyi.common.core.domain.entity.SysMenu;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.mapper.SysMenuMapper;
import com.ruoyi.system.service.ISysMenuService;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.stream.Collectors;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import javax.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

public class DemoIdentityTest {
    private final DemoIdentity projection = new DemoIdentity();
    private final Map<String, Object> admin = Collections.singletonMap("principalType", "ADMIN");
    private final Map<String, Object> node = Collections.singletonMap("principalType", "NODE");

    @Test
    public void adminRoutesProjectOnlyFourEntrancesWhileNodeTreeIsUnchanged() {
        SysMenuMapper mapper = mock(SysMenuMapper.class);
        ISysMenuService menus = mock(ISysMenuService.class);
        ReflectionTestUtils.setField(projection, "menuMapper", mapper);
        ReflectionTestUtils.setField(projection, "menus", menus);
        List<SysMenu> rows = new ArrayList<>();
        for (long id : new long[]{9470, 9103, 9005, 9006, 9201, 9431, 9260, 9440, 9412, 9460, 9280}) {
            SysMenu menu = new SysMenu();
            menu.setMenuId(id);
            menu.setStatus("0");
            menu.setMenuType("C");
            rows.add(menu);
        }
        when(mapper.selectMenuList(any(SysMenu.class))).thenReturn(rows);
        List<SysMenu> projected = projection.adminMenus();
        assertEquals(new HashSet<>(Arrays.asList(9470L, 9103L, 9005L, 9006L, 9201L, 9431L)),
                projected.stream().map(SysMenu::getMenuId).collect(Collectors.toSet()));
        when(menus.buildMenuTree(projected)).thenReturn(projected);
        LoginUser adminUser = new LoginUser();
        adminUser.setUserId(-1L);
        assertEquals(projected, projection.routes(adminUser));
        verify(menus).buildMenuTree(projected);
        when(menus.selectMenuTreeByUserId(42L)).thenReturn(rows);
        LoginUser nodeUser = new LoginUser();
        nodeUser.setUserId(42L);
        assertEquals(rows, projection.routes(nodeUser));
        verify(menus).selectMenuTreeByUserId(42L);
    }

    @Test
    public void adminCannotReadSingleKeysListsExportsOrPerformKeyWrites() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        for (String method : Arrays.asList("GET", "HEAD", "POST", "PUT", "DELETE")) {
            request.setMethod(method);
            for (String path : Arrays.asList("/generate/keymanage/list", "/generate/keymanage/123",
                    "/generate/keymanage/export", "/generate/keymanage", "/generate/user/register",
                    "/lifecycle/keys/123", "/monitor/operlog/list")) {
                request.setServletPath(path);
                assertFalse(projection.allowed(request, admin), method + " " + path);
            }
        }
    }

    @Test
    public void adminFrameworkReadsAreExactGetOnly() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        for (String path : Arrays.asList("/getInfo", "/getRouters", "/system/dict/data/type/key_status")) {
            request.setServletPath(path);
            request.setMethod("GET");
            assertTrue(projection.allowed(request, admin), path);
            for (String method : Arrays.asList("HEAD", "POST", "PUT", "DELETE")) {
                request.setMethod(method);
                assertFalse(projection.allowed(request, admin), method + " " + path);
            }
        }
        request.setMethod("GET");
        for (String path : Arrays.asList("/system/dict/data/type/", "/system/dict/data/type/key_status/extra",
                "/getInfo/extra", "/system/user/profile")) {
            request.setServletPath(path);
            assertFalse(projection.allowed(request, admin), path);
        }
    }

    @Test
    public void nodeGenerateListDetailCreateUpdateDeleteRemainAllowedButRegisterIsDenied() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        for (String method : Arrays.asList("GET", "POST", "PUT", "DELETE")) {
            request.setMethod(method);
            for (String path : Arrays.asList("/generate/keymanage/list", "/generate/keymanage/123",
                    "/generate/keymanage", "/lifecycle/keys/123")) {
                request.setServletPath(path);
                assertTrue(projection.allowed(request, node), method + " " + path);
            }
            request.setServletPath("/generate/user/register");
            assertFalse(projection.allowed(request, node));
        }
    }

    @Test
    public void authoritativeAdminFixtureIsRejectedByJwtDemoBranchBeforeControllerAndTokenFallback() throws Exception {
        for (String method : Arrays.asList("GET", "POST")) {
            for (String path : Arrays.asList("/generate/keymanage/list", "/generate/keymanage/123")) {
                MockHttpServletRequest request = new MockHttpServletRequest(method, path);
                request.setServletPath(path);
                request.addHeader("X-Kms-Demo-Revision", "7");
                request.addHeader("X-Kms-Demo-CSRF", "fixture-csrf");
                MockHttpServletResponse response = new MockHttpServletResponse();
                DemoBoundary boundary = mock(DemoBoundary.class);
                DemoSessionService sessions = mock(DemoSessionService.class);
                TokenService tokens = mock(TokenService.class);
                FilterChain chain = mock(FilterChain.class);
                JwtAuthenticationTokenFilter filter = new JwtAuthenticationTokenFilter();
                ReflectionTestUtils.setField(filter, "demoBoundary", boundary);
                ReflectionTestUtils.setField(filter, "demoSessions", sessions);
                ReflectionTestUtils.setField(filter, "demoIdentity", projection);
                ReflectionTestUtils.setField(filter, "tokenService", tokens);
                when(boundary.isDemo(request)).thenReturn(true);
                when(boundary.sessionId(request)).thenReturn("fixture-session");
                when(sessions.identity("fixture-session", "7", null)).thenReturn(admin);
                Map<String, Object> acquired = new HashMap<>();
                acquired.put("identity", admin);
                acquired.put("leaseId", "fixture-lease");
                when(sessions.acquire("fixture-session", "7", "fixture-csrf")).thenReturn(acquired);
                try {
                    filter.doFilter(request, response, chain);
                    assertEquals(403, response.getStatus(), method + " " + path);
                    assertTrue(response.getContentAsString().contains("DEMO_CAPABILITY_DENIED"));
                    verify(boundary).requireGateway(request);
                    verifyNoInteractions(chain, tokens);
                    if ("POST".equals(method)) verify(sessions).release("fixture-session", "fixture-lease");
                } finally {
                    SecurityContextHolder.clearContext();
                }
            }
        }
    }
}
