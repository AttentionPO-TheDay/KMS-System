package com.ruoyi.generate.controller;

import com.ruoyi.generate.domain.PermissionRequest;
import com.ruoyi.generate.service.PermissionRequestService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/permission/request")
public class PermissionRequestController {
    private final PermissionRequestService permissionRequestService;

    public PermissionRequestController(PermissionRequestService permissionRequestService) {
        this.permissionRequestService = permissionRequestService;
    }

    @GetMapping("/list")
    public ResponseEntity<Map<String, Object>> list(@RequestParam(required = false) Long userId,
                                                    @RequestParam(required = false) String status) {
        List<PermissionRequest> rows = permissionRequestService.list(userId, status);
        Map<String, Object> result = ok("查询成功");
        result.put("rows", rows);
        result.put("total", rows.size());
        return ResponseEntity.ok(result);
    }

    @GetMapping("/{requestId}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long requestId) {
        PermissionRequest data = permissionRequestService.get(requestId);
        if (data == null) {
            return ResponseEntity.status(404).body(error(404, "申请不存在"));
        }
        Map<String, Object> result = ok("查询成功");
        result.put("data", data);
        return ResponseEntity.ok(result);
    }

    @PostMapping("/submit")
    public ResponseEntity<Map<String, Object>> submit(@RequestBody PermissionRequest request) {
        try {
            permissionRequestService.submit(request);
            return ResponseEntity.ok(ok("提交成功"));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(error(400, ex.getMessage()));
        }
    }

    @PutMapping("/approve/{requestId}")
    public ResponseEntity<Map<String, Object>> approve(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            permissionRequestService.approve(requestId, request.getApproveBy(), request.getApproveNote());
            return ResponseEntity.ok(ok("审批通过"));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(error(400, ex.getMessage()));
        }
    }

    @PutMapping("/reject/{requestId}")
    public ResponseEntity<Map<String, Object>> reject(@PathVariable Long requestId, @RequestBody PermissionRequest request) {
        try {
            permissionRequestService.reject(requestId, request.getApproveBy(), request.getApproveNote());
            return ResponseEntity.ok(ok("审批拒绝"));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(error(400, ex.getMessage()));
        }
    }

    @PutMapping("/rollback/{requestId}")
    public ResponseEntity<Map<String, Object>> rollback(@PathVariable Long requestId) {
        try {
            permissionRequestService.rollback(requestId);
            return ResponseEntity.ok(ok("回退成功"));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(error(400, ex.getMessage()));
        }
    }

    private Map<String, Object> ok(String msg) {
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", msg);
        return result;
    }

    private Map<String, Object> error(int code, String msg) {
        Map<String, Object> result = new HashMap<>();
        result.put("code", code);
        result.put("msg", msg);
        return result;
    }
}
