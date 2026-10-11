package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.framework.web.service.DemoIdentity;
import com.ruoyi.updatedel.domain.AutoUpdateItem;
import com.ruoyi.updatedel.domain.AutoUpdateRun;
import com.ruoyi.updatedel.service.AutoUpdateRunService;
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * KMS-019：自动更新任务记录（轮次 + 逐密钥明细）。
 *
 * <p>路径前缀 {@code /lifecycle/auto-update} 与 {@code LifecycleKeyController} 的
 * {@code PUT /lifecycle/keymanage/auto-update}（逐密钥开关）**刻意分开**：
 * 那个是"改一把密钥的开关"，这里是"看任务跑了没有"。合成一个前缀会让
 * "auto-update" 同时指开关与任务，日后加路由必然踩到语义重叠。
 */
@RestController
@RequestMapping("/lifecycle/auto-update")
public class AutoUpdateRunController extends BaseController {

    private final AutoUpdateRunService autoUpdateRunService;

    public AutoUpdateRunController(AutoUpdateRunService autoUpdateRunService) {
        this.autoUpdateRunService = autoUpdateRunService;
    }

    /**
     * 轮次列表（倒序）。
     *
     * <p>收敛口径与 {@code KeyOperationRecordController#list} 一致：非管理员
     * 只能看到**影响过自己密钥**的轮次（一轮扫描会动很多人的密钥，
     * 全量放给普通用户等于把别人的密钥名/算法/失败原因一并交出去）。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/runs")
    public TableDataInfo runs(AutoUpdateRun query) {
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(autoUpdateRunService.listRuns(query));
    }

    /**
     * 单轮明细（分页）。{@code runId} 是路径参数，keyId / result 是可选筛选。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/runs/{runId}")
    public TableDataInfo runItems(@PathVariable String runId, AutoUpdateItem query) {
        query.setRunId(runId);
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
        }
        startPage();
        return getDataTable(autoUpdateRunService.listItems(query));
    }

    /**
     * 手动触发一轮（跑的是与定时任务**同一个** service 方法）。
     *
     * <p>仅管理员：它会真的轮换候选密钥（改版本、重算材料、发链上事件），
     * 不是只读操作。普通用户想立刻更新自己的密钥，走的是「密钥更新」页
     * （PUT /lifecycle/keymanage，带 rotate 标志）。
     */
    @PreAuthorize("isAuthenticated()")
    @PostMapping("/run-once")
    public AjaxResult runOnce() {
        if (!isCurrentAdmin()) {
            return AjaxResult.error("无权手动触发自动更新任务（仅平台管理员）");
        }
        AutoUpdateRun run = autoUpdateRunService.executeOnce(AutoUpdateRunService.TRIGGER_MANUAL);
        return AjaxResult.success("本轮自动更新已执行", run);
    }

    /**
     * 每把密钥的最近一条执行结果（keyautoupdate 页「上次执行」列）。
     *
     * <p>参数 {@code keyIds} 逗号分隔：页面把当前页的密钥 ID 一次带过来，
     * 避免"每行一个请求"的 N+1（那种写法在 10 行/页时看着没问题，
     * 翻到 50 行/页就是 50 个并发请求，而失败会表现为"部分行没有数据"）。
     * 上限在 service 里（200 个），超出部分静默丢弃是**不行**的 —— 页面
     * 只会看到"有些行是 -"，所以 controller 不截断请求，由 service 保证
     * 只处理前 200 个并按 keyId 返回，多出来的 keyId 页面自然显示 `-`。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/latest")
    public AjaxResult latest(@RequestParam(value = "keyIds", required = false) String keyIds) {
        List<Long> parsed = parseKeyIds(keyIds);
        // keyId 是可猜的数字，普通用户只能读自己作为属主的 item；
        // 管理员保留全量查询能力。
        Long ownerId = isCurrentAdmin() ? null : getUserId();
        return AjaxResult.success(autoUpdateRunService.latestByKeyIds(parsed, ownerId));
    }

    private List<Long> parseKeyIds(String raw) {
        List<Long> result = new ArrayList<>();
        if (raw == null || raw.trim().isEmpty()) {
            return result;
        }
        for (String part : raw.split(",")) {
            String trimmed = part.trim();
            if (trimmed.isEmpty()) {
                continue;
            }
            try {
                result.add(Long.valueOf(trimmed));
            } catch (NumberFormatException ignored) {
                // 非法项直接跳过：整串参数是一串 keyId，一个脏值不该让页面
                // 整列变成错误（那看起来像"这个功能没实现"）。
            }
        }
        return result;
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.isAdmin(getUserId()) || DemoIdentity.isCurrentAdmin();
    }
}