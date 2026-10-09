package com.ruoyi.framework.web.service;

import com.ruoyi.common.core.domain.entity.SysMenu;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.system.mapper.SysMenuMapper;
import com.ruoyi.system.service.ISysMenuService;
import com.ruoyi.system.service.ISysUserService;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class DemoIdentity {
    public static final String ATTRIBUTE = "kms.demo.identity";
    private static final Set<Long> ADMIN_MENUS = new HashSet<>(Arrays.asList(
            9260L, 9440L, 9441L, 9442L, 9021L, 9450L, 9451L, 9452L, 9412L, 9413L,
            9460L, 9101L, 9104L, 9105L, 9453L, 9470L, 9103L, 9005L, 9006L, 9461L, 9102L, 9280L));
    @Autowired private ISysUserService users;
    @Autowired private UserDetailsServiceImpl userDetails;
    @Autowired private ISysMenuService menus;
    @Autowired private SysMenuMapper menuMapper;

    public LoginUser project(Map<String, Object> identity) {
        if ("ADMIN".equals(identity.get("principalType"))) {
            SysUser user = new SysUser();
            user.setUserId(-1L);
            user.setUserName("DEMO_ADMIN");
            user.setNickName("演示管理员");
            user.setAvatar("");
            user.setPrincipalType("ADMIN");
            user.setRoleLevel(0);
            user.setStatus("0");
            user.setDelFlag("0");
            user.setRoles(new ArrayList<>());
            Set<String> permissions = new HashSet<>(Arrays.asList("monitor:operlog:list", "monitor:operlog:query"));
            for (SysMenu menu : adminMenus()) if (menu.getPerms() != null && !menu.getPerms().isEmpty()) {
                for (String perm : menu.getPerms().split(",")) if (!perm.contains("*")) permissions.add(perm);
            }
            return new LoginUser(-1L, null, user, permissions);
        }
        Long userId = Long.valueOf(String.valueOf(identity.get("userId")));
        SysUser user = users.selectUserById(userId);
        if (user == null || user.isAdmin() || !"NODE".equals(user.getPrincipalType())
                || !"0".equals(user.getStatus()) || !"0".equals(user.getDelFlag())) {
            throw new IllegalArgumentException("DEMO_NODE_ACCOUNT_INVALID");
        }
        if (user.getAvatar() == null) user.setAvatar("");
        return (LoginUser) userDetails.createLoginUser(user);
    }

    public static boolean isCurrentAdmin() {
        javax.servlet.http.HttpServletRequest request = com.ruoyi.common.utils.ServletUtils.getRequest();
        Object raw = request == null ? null : request.getAttribute(ATTRIBUTE);
        return raw instanceof Map && "ADMIN".equals(((Map) raw).get("principalType"))
                && Long.valueOf(-1L).equals(com.ruoyi.common.utils.SecurityUtils.getUserId());
    }

    public List<SysMenu> adminMenus() {
        List<SysMenu> result = new ArrayList<>();
        for (SysMenu menu : menuMapper.selectMenuList(new SysMenu())) {
            if (ADMIN_MENUS.contains(menu.getMenuId()) && "0".equals(menu.getStatus()) && !"F".equals(menu.getMenuType())) result.add(menu);
        }
        return result;
    }

    public List<SysMenu> routes(LoginUser user) {
        return user.getUserId() == -1L ? menus.buildMenuTree(adminMenus()) : menus.selectMenuTreeByUserId(user.getUserId());
    }

    public boolean allowed(javax.servlet.http.HttpServletRequest request, Map<String, Object> identity) {
        String path = request.getServletPath();
        boolean mutation = DemoBoundary.mutation(request);
        if (path.equals("/getInfo") || path.equals("/getRouters")) return !mutation;
        if (path.equals("/system/user/profile")) return !mutation && "NODE".equals(identity.get("principalType"));
        if (path.startsWith("/system/dict/data/type/")) return !mutation;
        if (path.equals("/monitor/operlog/list")) return !mutation && "ADMIN".equals(identity.get("principalType"));
        if (path.startsWith("/generate/") || path.startsWith("/lifecycle/")) {
            if (path.equals("/generate/user/register")) return false;
            return !mutation || "NODE".equals(identity.get("principalType"));
        }
        return false;
    }
}
