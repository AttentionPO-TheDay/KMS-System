package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.framework.web.service.DemoIdentity;
import com.ruoyi.updatedel.domain.KeyHealthScanItem;
import com.ruoyi.updatedel.domain.KeyHealthScanRun;
import com.ruoyi.updatedel.service.KeyHealthScanService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * KMS-022：批量一致性检查（用户密钥侧）。
 *
 * <p>为什么**另建** controller 而不是往 {@code LifecycleKeyController} 里加：
 * KMS-019 已经改过那个文件的 auto-update 守卫，两条车道并行施工时同一文件
 * 是两个改动面（计划 §7.1 第 4 条）。新端点在语义上也是独立的一组
 * （扫描批次是可回看的对象，不是"某把密钥"的子资源）。
 *
 * <h2>路径与既有单钥端点共存</h2>
 * 本类挂在 {@code /lifecycle/keymanage/health} 下，与
 * {@code LifecycleKeyController} 的 {@code GET /lifecycle/keymanage/health/{keyId}}
 * **同前缀**。Spring MVC 的路径匹配对字面量优先于模板变量，因此
 * {@code /health/scans} 落到本类、{@code /health/123} 落到单钥端点；
 * 这一点由验收脚本用真实 HTTP 断言（而不是"看着应该没问题"）。
 *
 * <h2>权限</h2>
 * 普通用户的分批扫描只扫**自己**的密钥（Controller 强制收敛）；
 * 指定他人 userId 的全量/定向扫描仅平台管理员可用，且拒绝时给明确文案。
 */
@RestController
@RequestMapping("/lifecycle/keymanage/health")
public class KeyHealthScanController extends BaseController {

    private final KeyHealthScanService keyHealthScanService;

    public KeyHealthScanController(KeyHealthScanService keyHealthScanService) {
        this.keyHealthScanService = keyHealthScanService;
    }

    /**
     * 触发一轮批量扫描。
     *
     * @param userId 可选；仅管理员可指定（扫某一个用户的密钥）。
     *               普通用户无论传什么都只会扫自己的 —— 但**传了别人的会被明确拒绝**，
     *               而不是静默改成扫自己：静默改写会让调用方以为"全库扫过了"。
     */
    @PreAuthorize("isAuthenticated()")
    @PostMapping("/scan")
    public AjaxResult scan(@RequestParam(value = "userId", required = false) Long userId) {
        boolean admin = isCurrentAdmin();
        if (!admin && userId != null && !userId.equals(getUserId())) {
            return AjaxResult.error("无权扫描他人的密钥（仅平台管理员可指定用户）");
        }
        Long scopeUserId = admin ? userId : getUserId();
        KeyHealthScanRun run = keyHealthScanService.scan(scopeUserId);
        return AjaxResult.success("扫描完成", run);
    }

    /** 批次列表（倒序）。非管理员收敛为"属于自己或扫过自己密钥"的批次。 */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/scans")
    public TableDataInfo scans(KeyHealthScanRun query) {
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(keyHealthScanService.listRuns(query));
    }

    /** 单批明细（分页；verdict / keyId 可选筛选）。 */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/scans/{runId}")
    public TableDataInfo scanItems(@PathVariable String runId, KeyHealthScanItem query) {
        query.setRunId(runId);
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(keyHealthScanService.listItems(query));
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.isAdmin(getUserId()) || DemoIdentity.isCurrentAdmin();
    }
}