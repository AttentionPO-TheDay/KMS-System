package com.ruoyi.generate.controller;

import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.service.GenerateUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/generate/user")
public class GenerateUserController {

    @Autowired
    private GenerateUserService generateUserService;

    @PostMapping("/register")
    public ResponseEntity<Map<String, Object>> register(@RequestBody Map<String, String> request) {
        String userName = request.get("user");
        String password = request.get("password");

        Map<String, Object> result = new HashMap<>();
        if (userName == null || userName.trim().isEmpty() || password == null || password.trim().isEmpty()) {
            result.put("code", 500);
            result.put("msg", "用户名或密码不能为空");
            return ResponseEntity.badRequest().body(result);
        }

        if (generateUserService.selectByUserName(userName) != null) {
            result.put("code", 500);
            result.put("msg", "注册失败: 已包含该用户");
            return ResponseEntity.ok(result);
        }

        int rows = generateUserService.register(userName, password);
        result.put("code", rows > 0 ? 200 : 500);
        result.put("msg", rows > 0 ? "操作成功" : "注册失败");
        return ResponseEntity.ok(result);
    }

    @GetMapping("/non-admin-list")
    public ResponseEntity<Map<String, Object>> nonAdminList() {
        List<GenerateUser> users = generateUserService.selectNonAdminUsers();
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", users);
        return ResponseEntity.ok(result);
    }

    @GetMapping("/profile")
    public ResponseEntity<Map<String, Object>> profile(@RequestParam(required = false) Long userId,
                                                       @RequestParam(required = false) String userName) {
        GenerateUser user = null;
        if (userId != null) {
            user = generateUserService.selectByUserId(userId);
        } else if (userName != null && !userName.trim().isEmpty()) {
            user = generateUserService.selectByUserName(userName);
        }

        Map<String, Object> result = new HashMap<>();
        if (user == null) {
            result.put("code", 404);
            result.put("msg", "用户不存在");
            return ResponseEntity.status(404).body(result);
        }

        user.setPassword(null);
        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", user);
        return ResponseEntity.ok(result);
    }
}
