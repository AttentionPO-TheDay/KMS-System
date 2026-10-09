package com.ruoyi.web.controller.system;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.framework.web.service.DemoBoundary;
import com.ruoyi.framework.web.service.DemoSessionService;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/demo/context")
public class DemoContextController {
    @Autowired private DemoBoundary boundary;
    @Autowired private DemoSessionService sessions;

    @GetMapping
    public AjaxResult context(HttpServletRequest request) {
        try {
            boundary.requireGateway(request);
            String id = boundary.sessionId(request);
            return AjaxResult.success(id == null ? sessions.initial() : sessions.context(id));
        } catch (IllegalArgumentException ex) { return failure(ex.getMessage()); }
    }

    @PostMapping("/{action:entry|admin|node|logout}")
    public AjaxResult change(@PathVariable String action, @RequestBody(required = false) Map<String, Object> body,
                             HttpServletRequest request, HttpServletResponse response) {
        try {
            boundary.requireGateway(request);
            boundary.requireOrigin(request);
            String id = boundary.sessionId(request);
            String csrf = request.getHeader("X-Kms-Demo-CSRF");
            String revision = request.getHeader("X-Kms-Demo-Revision");
            if (id == null) {
                if (!"entry".equals(action) && !"admin".equals(action)) throw new IllegalArgumentException("DEMO_SESSION_INVALID");
                id = DemoSessionService.opaque();
                Map<String, Object> state = sessions.initial();
                sessions.save(id, state);
                csrf = (String) state.get("csrfToken");
                revision = "0";
                cookie(response, id, 28800);
            }
            String nodeId = body == null || body.get("nodeId") == null ? null : String.valueOf(body.get("nodeId"));
            Map<String, Object> state = sessions.change(id, action, nodeId, csrf, revision);
            if ("logout".equals(action)) cookie(response, "", 0);
            if (state.get("errorCode") != null) {
                AjaxResult result = failure(String.valueOf(state.get("errorCode")));
                result.put("data", state);
                return result;
            }
            return AjaxResult.success(state);
        } catch (IllegalArgumentException ex) { return failure(ex.getMessage()); }
    }

    private void cookie(HttpServletResponse response, String id, int maxAge) {
        response.addHeader("Set-Cookie", DemoBoundary.COOKIE + "=" + id + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" + maxAge
                + (boundary.isSecure() ? "; Secure" : ""));
    }

    private AjaxResult failure(String code) {
        AjaxResult result = AjaxResult.error(403, code);
        result.put("errorCode", code);
        return result;
    }
}
