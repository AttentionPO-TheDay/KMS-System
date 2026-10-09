package com.ruoyi.web.controller.system;

import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.constant.Constants;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.domain.entity.SysMenu;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginBody;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.framework.web.service.SysLoginService;
import com.ruoyi.framework.web.service.SysPermissionService;
import com.ruoyi.framework.web.service.TokenService;
import com.ruoyi.system.service.ISysMenuService;
import com.ruoyi.system.service.ISysUserService;

/**
 * 登录验证
 * 
 * @author ruoyi
 */
@RestController
public class SysLoginController {
    @Autowired
    private SysLoginService loginService;

    @Autowired
    private ISysMenuService menuService;

    @Autowired
    private SysPermissionService permissionService;

    @Autowired
    private TokenService tokenService;

    @Autowired
    private ISysUserService userService;

    @Autowired
    private com.ruoyi.framework.web.service.DemoIdentity demoIdentity;

    /**
     * 登录方法
     * 
     * @param loginBody 登录信息
     * @return 结果
     */
    @PostMapping("/login")
    public AjaxResult login(@RequestBody LoginBody loginBody) {
        AjaxResult ajax = AjaxResult.success();
        // 生成令牌
        String token = loginService.login(loginBody.getUsername(), loginBody.getPassword(), loginBody.getCode(),
                loginBody.getUuid());
        ajax.put(Constants.TOKEN, token);
        return ajax;
    }

    /**
     * 获取用户信息
     * 
     * @return 用户信息
     */
    @GetMapping("getInfo")
    public AjaxResult getInfo(javax.servlet.http.HttpServletRequest request) {
        LoginUser loginUser = SecurityUtils.getLoginUser();
        if (request.getAttribute(com.ruoyi.framework.web.service.DemoIdentity.ATTRIBUTE) != null) {
            AjaxResult ajax = AjaxResult.success();
            ajax.put("user", loginUser.getUser());
            ajax.put("roles", java.util.Collections.singleton(loginUser.getUserId() == -1L ? "demo_admin" : "node"));
            ajax.put("permissions", loginUser.getPermissions());
            ajax.put("entryMode", "DEMO");
            return ajax;
        }
        Long userId = loginUser.getUserId();

        // 从数据库重新查询用户信息，确保获取最新的 role_level
        SysUser user = userService.selectUserById(userId);
        if (user == null) {
            user = loginUser.getUser();
        } else {
            // 更新 loginUser 中的用户信息
            loginUser.setUser(user);
        }

        // 角色集合
        Set<String> roles = permissionService.getRolePermission(user);
        // 权限集合
        Set<String> permissions = permissionService.getMenuPermission(user);
        if (!loginUser.getPermissions().equals(permissions)) {
            loginUser.setPermissions(permissions);
            tokenService.refreshToken(loginUser);
        }
        AjaxResult ajax = AjaxResult.success();
        ajax.put("user", user);
        ajax.put("roles", roles);
        ajax.put("permissions", permissions);
        return ajax;
    }

    /**
     * 获取路由信息
     * 
     * @return 路由信息
     */
    @GetMapping("getRouters")
    public AjaxResult getRouters(javax.servlet.http.HttpServletRequest request) {
        if (request.getAttribute(com.ruoyi.framework.web.service.DemoIdentity.ATTRIBUTE) != null) {
            return AjaxResult.success(menuService.buildMenus(demoIdentity.routes(SecurityUtils.getLoginUser())));
        }
        Long userId = SecurityUtils.getUserId();
        List<SysMenu> menus = menuService.selectMenuTreeByUserId(userId);
        return AjaxResult.success(menuService.buildMenus(menus));
    }
}
