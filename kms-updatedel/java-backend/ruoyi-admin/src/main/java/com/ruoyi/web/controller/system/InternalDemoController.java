package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.framework.web.service.DemoBoundary;
import com.ruoyi.framework.web.service.DemoSessionService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/lifecycle/demo")
public class InternalDemoController {
    @Autowired private DemoBoundary boundary;
    @Autowired private DemoSessionService sessions;

    @PostMapping("/{operation:introspect}")
    public AjaxResult invoke(@PathVariable String operation,
                            @RequestHeader(value = "X-Internal-Token", required = false) String token,
                            @RequestBody Map<String, Object> body) {
        return execute(operation, token, body);
    }

    @PostMapping("/lease/{operation:acquire|validate|release}")
    public AjaxResult lease(@PathVariable String operation,
                           @RequestHeader(value = "X-Internal-Token", required = false) String token,
                           @RequestBody Map<String, Object> body) {
        return execute("lease/" + operation, token, body);
    }

    private AjaxResult execute(String operation, String token, Map<String, Object> body) {
        try {
            boundary.requireInternal(token);
            String id = string(body.get("sessionId"));
            if ("introspect".equals(operation)) return AjaxResult.success(sessions.identity(id, body.get("revision"), body.get("csrfToken")));
            if ("lease/acquire".equals(operation)) return AjaxResult.success(sessions.acquire(id, body.get("revision"), body.get("csrfToken")));
            String lease = string(body.get("leaseId"));
            Map<String, Object> result = new LinkedHashMap<>();
            if ("lease/validate".equals(operation)) {
                result.put("ok", sessions.validate(id, lease));
                if (!Boolean.TRUE.equals(result.get("ok"))) result.put("errorCode", "DEMO_LEASE_EXPIRED");
            } else if ("lease/release".equals(operation)) {
                sessions.release(id, lease);
                result.put("ok", true);
            } else throw new IllegalArgumentException("DEMO_ACTION_INVALID");
            return AjaxResult.success(result);
        } catch (IllegalArgumentException ex) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("ok", false);
            result.put("errorCode", ex.getMessage());
            result.put("errorMessage", ex.getMessage());
            return AjaxResult.success(result);
        }
    }

    private String string(Object value) { return value == null ? null : String.valueOf(value); }
}
