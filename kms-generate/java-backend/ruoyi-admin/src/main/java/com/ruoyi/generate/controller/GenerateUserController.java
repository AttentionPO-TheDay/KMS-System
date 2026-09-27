package com.ruoyi.generate.controller;

import com.ruoyi.common.annotation.Anonymous;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.service.GenerateUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/generate/user")
public class GenerateUserController extends BaseController {

    @Autowired
    private GenerateUserService generateUserService;

    @Anonymous
    @PostMapping("/register")
    public AjaxResult register(@RequestBody Map<String, String> request) {
        String userName = request.get("user");
        String password = request.get("password");

        if (userName == null || userName.trim().isEmpty() || password == null || password.trim().isEmpty()) {
            return error("用户名或密码不能为空");
        }

        if (generateUserService.selectByUserName(userName) != null) {
            return error("注册失败: 已包含该用户");
        }

        int rows = generateUserService.register(userName, password);
        return rows > 0 ? success("操作成功") : error("注册失败");
    }

    /**
     * 用户列表属于管理面能力，仅管理员可访问。
     * 此前无鉴权，任意登录用户可枚举全部用户名（后续可据此伪造归属）。
     */
    @PreAuthorize("@ss.hasRole('admin')")
    @GetMapping("/non-admin-list")
    public AjaxResult nonAdminList() {
        List<GenerateUser> users = generateUserService.selectNonAdminUsers();
        return AjaxResult.success("查询成功", users);
    }

    /**
     * 查询用户资料：非管理员只能查询本人，防止任意读取他人资料。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/profile")
    public AjaxResult profile(@RequestParam(required = false) Long userId,
                              @RequestParam(required = false) String userName) {
        if (!isCurrentAdmin()) {
            Long currentUserId = getUserId();
            String currentUserName = getUsername();
            boolean selfById = userId != null && userId.equals(currentUserId);
            boolean selfByName = userName != null && !userName.trim().isEmpty()
                && userName.trim().equals(currentUserName);
            if (!selfById && !selfByName) {
                return AjaxResult.error(403, "无权查询其他用户资料");
            }
        }

        GenerateUser user = null;
        if (userId != null) {
            user = generateUserService.selectByUserId(userId);
        } else if (userName != null && !userName.trim().isEmpty()) {
            user = generateUserService.selectByUserName(userName);
        }

        if (user == null) {
            return AjaxResult.error(404, "用户不存在");
        }

        user.setPassword(null);
        return AjaxResult.success("查询成功", user);
    }

    private boolean isCurrentAdmin() {
        try {
            return SecurityUtils.getLoginUser() != null
                && SecurityUtils.getLoginUser().getUser() != null
                && SecurityUtils.getLoginUser().getUser().isAdmin();
        } catch (Exception e) {
            return false;
        }
    }
}
