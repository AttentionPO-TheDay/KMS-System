package com.ruoyi.framework.web.service;

import com.ruoyi.common.core.domain.entity.SysMenu;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.mapper.SysMenuMapper;
import com.ruoyi.system.service.ISysMenuService;
import java.util.*;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

public class DemoIdentityTest {
    @Test
    public void adminMenuProjectionContainsCategorizedReadOnlyEntrances() {
        DemoIdentity identity = new DemoIdentity();
        SysMenuMapper mapper = mock(SysMenuMapper.class);
        ISysMenuService menus = mock(ISysMenuService.class);
        ReflectionTestUtils.setField(identity, "menuMapper", mapper);
        ReflectionTestUtils.setField(identity, "menus", menus);
        List<SysMenu> rows = new ArrayList<>();
        for (long id : new long[]{9470, 9103, 9005, 9006, 9201,
                9480, 9481, 9482, 9483, 9484, 9461, 9453,
                9431, 9260, 9440, 9412, 9460, 9280}) {
            SysMenu menu = new SysMenu();
            menu.setMenuId(id);
            menu.setStatus("0");
            menu.setMenuType("C");
            rows.add(menu);
        }
        when(mapper.selectMenuList(any(SysMenu.class))).thenReturn(rows);
        List<SysMenu> projected = identity.adminMenus();
        assertEquals(new HashSet<>(Arrays.asList(9470L, 9103L, 9005L, 9006L, 9201L,
                        9480L, 9481L, 9482L, 9483L, 9484L, 9461L, 9453L)),
                projected.stream().map(SysMenu::getMenuId).collect(Collectors.toSet()));
        when(menus.buildMenuTree(any())).thenReturn(projected);
        LoginUser admin = new LoginUser();
        admin.setUserId(-1L);
        assertEquals(projected, identity.routes(admin));
        verify(menus).buildMenuTree(projected);
        verify(menus, never()).selectMenuTreeByUserId(-1L);
        rows.get(0).setStatus("1");
        rows.get(1).setMenuType("F");
        assertEquals(10, identity.adminMenus().size());
    }

    @Test
    public void adminCannotReadOrExportKeysOrWriteHiddenBusinessEndpoints() {
        DemoIdentity identity = new DemoIdentity();
        Map<String, Object> admin = Collections.singletonMap("principalType", "ADMIN");
        MockHttpServletRequest request = new MockHttpServletRequest();
        for (String method : Arrays.asList("GET", "HEAD", "POST", "PUT", "DELETE")) {
            request.setMethod(method);
            for (String path : Arrays.asList("/generate/keymanage/list", "/generate/keymanage/1",
                    "/generate/keymanage/export", "/lifecycle/keys/1", "/lifecycle/dashboard/summary",
                    "/monitor/operlog/list", "/system/user/list")) {
                request.setServletPath(path);
                assertFalse(identity.allowed(request, admin), method + " " + path);
            }
        }
        request.setMethod("GET");
        for (String path : Arrays.asList("/getInfo", "/getRouters", "/system/dict/data/type/key_status")) {
            request.setServletPath(path);
            assertTrue(identity.allowed(request, admin), path);
            request.setMethod("POST");
            assertFalse(identity.allowed(request, admin), path);
            request.setMethod("GET");
        }
        request.setServletPath("/generate/keymanage/list");
        assertTrue(identity.allowed(request, Collections.singletonMap("principalType", "NODE")));
        request.setMethod("POST");
        assertTrue(identity.allowed(request, Collections.singletonMap("principalType", "NODE")));
    }
}
