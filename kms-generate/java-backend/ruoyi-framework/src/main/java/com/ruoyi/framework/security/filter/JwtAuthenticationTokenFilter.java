package com.ruoyi.framework.security.filter;

import java.io.IOException;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.StringUtils;
import com.ruoyi.framework.web.service.TokenService;

/**
 * token过滤器 验证token有效性
 * 
 * @author ruoyi
 */
@Component
public class JwtAuthenticationTokenFilter extends OncePerRequestFilter
{
    @Autowired
    private TokenService tokenService;

    @Autowired
    private com.ruoyi.framework.web.service.DemoBoundary demoBoundary;
    @Autowired
    private com.ruoyi.framework.web.service.DemoSessionService demoSessions;
    @Autowired
    private com.ruoyi.framework.web.service.DemoIdentity demoIdentity;
    private static final java.util.concurrent.ScheduledExecutorService DEMO_RENEW = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
        Thread thread = new Thread(r, "demo-lease-renew");
        thread.setDaemon(true);
        return thread;
    });

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException
    {
        if (demoBoundary.isDemo(request) || request.getServletPath().startsWith("/demo/"))
        {
            doDemo(request, response, chain);
            return;
        }
        LoginUser loginUser = tokenService.getLoginUser(request);
        if (StringUtils.isNotNull(loginUser) && StringUtils.isNull(SecurityUtils.getAuthentication()))
        {
            tokenService.verifyToken(loginUser);
            UsernamePasswordAuthenticationToken authenticationToken = new UsernamePasswordAuthenticationToken(loginUser, null, loginUser.getAuthorities());
            authenticationToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
            SecurityContextHolder.getContext().setAuthentication(authenticationToken);
        }
        chain.doFilter(request, response);
    }

    private void doDemo(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException
    {
        String id = demoBoundary.sessionId(request);
        String lease = null;
        boolean contextRequest = request.getServletPath().equals("/demo/context")
                || request.getServletPath().startsWith("/demo/context/");
        try
        {
            demoBoundary.requireGateway(request);
            if (contextRequest) throw new IllegalArgumentException("DEMO_CONTEXT_LIFECYCLE_ONLY");
            SecurityContextHolder.clearContext();
            if (!contextRequest)
            {
                String revision = request.getHeader("X-Kms-Demo-Revision");
                if (revision == null) throw new IllegalArgumentException("DEMO_REVISION_REQUIRED");
                java.util.Map<String, Object> identity;
                if (com.ruoyi.framework.web.service.DemoBoundary.mutation(request))
                {
                    demoBoundary.requireOrigin(request);
                    java.util.Map<String, Object> acquired = demoSessions.acquire(id, revision, request.getHeader("X-Kms-Demo-CSRF"));
                    lease = String.valueOf(acquired.get("leaseId"));
                    identity = (java.util.Map<String, Object>) acquired.get("identity");
                }
                else identity = demoSessions.identity(id, revision, null);
                if (!demoIdentity.allowed(request, identity))
                    throw new IllegalArgumentException("DEMO_CAPABILITY_DENIED");
                LoginUser loginUser = demoIdentity.project(identity);
                request.setAttribute(com.ruoyi.framework.web.service.DemoIdentity.ATTRIBUTE, identity);
                UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(loginUser, null, loginUser.getAuthorities());
                authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                SecurityContextHolder.getContext().setAuthentication(authentication);
            }
        }
        catch (IllegalArgumentException ex)
        {
            if (lease != null) demoSessions.release(id, lease);
            response.setStatus(403);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(com.alibaba.fastjson2.JSON.toJSONString(com.ruoyi.common.core.domain.AjaxResult.error(403, ex.getMessage())));
            return;
        }
        final String heldLease = lease;
        java.util.concurrent.ScheduledFuture<?> renewal = lease == null ? null : DEMO_RENEW.scheduleAtFixedRate(
                () -> demoSessions.validate(id, heldLease), 60, 60, java.util.concurrent.TimeUnit.SECONDS);
        try { chain.doFilter(request, response); }
        finally
        {
            if (renewal != null) renewal.cancel(false);
            if (lease != null) demoSessions.release(id, lease);
            SecurityContextHolder.clearContext();
        }
    }
}
