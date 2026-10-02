package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.service.ISysUserService;
import com.ruoyi.updatedel.domain.KeyAnalysisResultDto;
import com.ruoyi.updatedel.domain.KeyHealthResult;
import com.ruoyi.updatedel.domain.KeyStatus;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.KeyHealthService;
import com.ruoyi.updatedel.service.KeyValueSanitizer;
import com.ruoyi.updatedel.service.LifecycleService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/lifecycle/keymanage")
public class LifecycleKeyController extends BaseController {
    private static final Logger log = LoggerFactory.getLogger(LifecycleKeyController.class);

    private final LifecycleService lifecycleService;
    private final KeyHealthService keyHealthService;
    private final ISysUserService userService;

    public LifecycleKeyController(LifecycleService lifecycleService,
                                  KeyHealthService keyHealthService,
                                  ISysUserService userService) {
        this.lifecycleService = lifecycleService;
        this.keyHealthService = keyHealthService;
        this.userService = userService;
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            query.setUserId(getUserId());
        }
        query.setStatus(normalizeStatusQuery(query.getStatus()));
        startPage();
        List<Keymanage> list = lifecycleService.list(query);
        // 列表一律不带密钥材料（见 KeyValueSanitizer 的说明）。
        // 已核对现网页面：生命周期相关的列表都不消费 keyValue；
        // 「更新」「安全分析」走的是更新响应与详情接口。
        KeyValueSanitizer.stripMaterial(list);
        return getDataTable(list);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult getInfo(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                KeyValueSanitizer.sanitizeDetail(key, isOwner);
                return AjaxResult.success(key);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    /**
     * 阶段 4（文档 §5.2）：历史版本列表。
     *
     * <p>准入与脱敏必须和 {@link #getInfo} **完全一致** —— 历史快照里同样含
     * KGC 部分密钥（{@code key_value}）与公钥份额（{@code ua}）。
     * 这里若省掉 {@code canAccess} 或 {@code sanitizeDetail}，
     * 就等于开了一条"用别人 key_id 读其历史密钥材料"的旁路。
     *
     * <p>按版本号倒序返回，**不含当前版本**（当前版本走 {@code /{keyId}}）。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}/versions")
    public AjaxResult getVersionHistory(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                List<Keymanage> history = lifecycleService.findVersionHistory(keyId);
                for (Keymanage snapshot : history) {
                    KeyValueSanitizer.sanitizeDetail(snapshot, isOwner);
                }
                return AjaxResult.success(history);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    /**
     * 阶段 7（文档 §8.1 + §8.2）：单把密钥的健康检查。
     *
     * <p>一致性检查与异常检测合并成一个接口 —— 两者读同一份数据，
     * 分开只会把同样的表扫两遍，且可能给出互相矛盾的结论。
     *
     * <p>准入与 {@link #getInfo} 一致：健康检查会读到 ua/keyValue 的存在与长度
     * 并回显，不校验属主就成了"用别人 keyId 探测其密钥材料是否齐备"的旁路。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/health/{keyId}")
    public AjaxResult getHealth(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权访问该密钥数据");
                }
                KeyHealthResult result = keyHealthService.check(keyId);
                if (result == null) {
                    return AjaxResult.error("密钥不存在: " + keyId);
                }
                // 观测值里含 ua/keyValue 的长度信息；非属主只保留结论，
                // 去掉带材料细节的观测，避免侧面泄露。
                boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                if (!isOwner) {
                    result.getObservations().removeIf(o -> o.contains("ua ") || o.contains("keyValue "));
                }
                return AjaxResult.success(result);
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/analysis/{keyId}")
    public AjaxResult getAnalysis(@PathVariable Long keyId) {
        return lifecycleService.findById(keyId)
            .map(key -> {
                if (!canAccess(key)) {
                    return AjaxResult.error("无权分析该密钥数据");
                }
                try {
                    KeyAnalysisResultDto analysis = lifecycleService.getAssociationAnalysis(keyId);
                    // 该 DTO 的 baseInfo 里嵌着整条 Keymanage（含 key_value），同样要脱敏，
                    // 否则"安全分析"会变成绕过列表脱敏的后门。
                    if (analysis != null && analysis.getBaseInfo() != null) {
                        boolean isOwner = key.getUserId() != null && key.getUserId().equals(getUserId());
                        KeyValueSanitizer.sanitizeDetail(analysis.getBaseInfo(), isOwner);
                    }
                    return AjaxResult.success(analysis);
                } catch (Exception e) {
                    log.error("密钥关联分析异常: keyId={}", keyId, e);
                    return AjaxResult.error("分析失败: " + e.getMessage());
                }
            })
            .orElseGet(() -> AjaxResult.error("密钥不存在: " + keyId));
    }

    /**
     * 新建密钥。
     *
     * <p>属主**只能来自令牌**，不能来自请求体。原先的写法只在请求没带 userId 时才
     * 回填当前用户，于是任何登录用户 POST 一个别人的 userId，就能把新密钥记在
     * 别人名下（并在响应里拿到自己生成的那份材料）。已核对全部调用方：
     * 前端只走 {@code /generate/keymanage}，脚本一律用管理员令牌显式指定属主。
     *
     * <p>因此按主体分流：
     * <ul>
     *   <li>非管理员：属主强制为令牌持有者，请求体里的 userId/userName 一律忽略；</li>
     *   <li>管理员：允许代建（脚本与运维需要），但目标账号必须真实存在，
     *       否则直接报错，而不是让外键在插入时才失败。</li>
     * </ul>
     *
     * <p>响应与 {@link #getInfo} 同口径做脱敏：调用方拿到的是自己刚生成的记录，
     * 但"创建响应"不该成为 list/detail 之外第三条返回密钥材料的通道。
     */
    @PreAuthorize("isAuthenticated()")
    @PostMapping
    public AjaxResult create(@RequestBody Keymanage request) {
        if (!SecurityUtils.isAdmin(getUserId())) {
            request.setUserId(getUserId());
            request.setUserName(getUsername());
        } else if (request.getUserId() != null) {
            SysUser owner = userService.selectUserById(request.getUserId());
            if (owner == null) {
                return AjaxResult.error("指定的密钥属主不存在: " + request.getUserId());
            }
            if (request.getUserName() == null || request.getUserName().trim().isEmpty()) {
                request.setUserName(owner.getUserName());
            }
        }
        if (request.getUserName() == null || request.getUserName().trim().isEmpty()) {
            request.setUserName(getUsername());
        }
        try {
            log.info("密钥新建: userId={}, encrytName={}", request.getUserId(), request.getEncrytName());
            Keymanage created = lifecycleService.createKey(request);
            KeyValueSanitizer.sanitizeDetail(created, true);
            return AjaxResult.success("密钥创建成功", created);
        } catch (Exception e) {
            log.error("密钥新建异常", e);
            return AjaxResult.error("密钥创建失败: " + e.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping
    public AjaxResult update(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        Keymanage current = lifecycleService.findById(request.getKeyId()).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + request.getKeyId());
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权修改该密钥");
        }

        // 阶段 8：此处原本还有一道 canManageAutoUpdate() 检查 —— 当 autoUpdate 的
        // 值真的变化时，要求调用方是管理员或持有临时审批授权。
        //
        // 现在去掉那一道，理由有两条，缺一不可：
        //   1. **临时审批流已整体删除**。它并不真正授予权限
        //      （PermissionRequestService 自己注明「刻意不调用 updateRoleLevel」），
        //      保留只会形成第二套权限语义 —— 节点权限现由
        //      principal_type + 资源属主直接决定。
        //   2. **属主校验才是真闸门**：上面第 192 行的 canAccess 已经保证
        //      只有属主或管理员能走到这里。原检查在属主身上再加一道，
        //      实际效果是"自己的密钥却不能改自己的自动更新设置"。
        //
        // ⚠️ 这与上面那段注释里写的"防绕过的本意保留"并不冲突：
        //    防的是**非属主**借改元数据之名打开自动更新 —— 那个由 canAccess 挡住。

        // 分流依据：是否要求**刷新密钥材料**。
        //
        // 阶段 4（文档 §5.3）把这个判断从"有没有 ua"改成了显式的 `rotate` 标志，
        // 理由是 ua 的**存在本身**已经不能表达这个意图了：§5.3 要求更新时
        // **保留** uA（只换 KGC 那一半），所以正常的部分刷新请求里
        // 带的正是与库里相同的 uA —— 旧判据会把它读成"换新 uA → 要轮换"，
        // 而"只改个名字"的请求一旦顺手把库里的 uA 回填回来，也会被误判成轮换。
        // 两种误判方向相反，却都由同一个含糊的信号产生。
        // 现在由调用方明确声明意图，ua 只用于校验（必须与库中一致，见 rotateKey）。
        if (!lifecycleService.requiresRotation(request)) {
            try {
                Keymanage updated = lifecycleService.updateMetadata(request);
                return AjaxResult.success("密钥信息更新成功", updated);
            } catch (IllegalStateException e) {
                log.warn("密钥信息更新失败: keyId={}, error={}", request.getKeyId(), e.getMessage());
                return AjaxResult.error(e.getMessage());
            }
        }

        // Synchronous key rotation
        try {
            log.info("密钥轮换: keyId={}, userId={}", request.getKeyId(), getUserId());
            Keymanage rotated = lifecycleService.rotateKey(request);
            return AjaxResult.success("密钥轮换成功", rotated);
        } catch (IllegalStateException e) {
            log.warn("密钥轮换失败: keyId={}, error={}", request.getKeyId(), e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            log.error("密钥轮换异常: keyId={}", request.getKeyId(), e);
            return AjaxResult.error("密钥轮换失败: " + e.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @PutMapping("/auto-update")
    public AjaxResult updateAutoUpdate(@RequestBody Keymanage request) {
        if (request.getKeyId() == null) {
            return AjaxResult.error("keyId 不能为空");
        }
        Keymanage current = lifecycleService.findById(request.getKeyId()).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + request.getKeyId());
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权修改该密钥");
        }
        if (KeyStatus.REVOKED.getCode().equals(current.getStatus())) {
            return AjaxResult.error("该密钥已被回收，无法修改自动更新状态");
        }
        // 阶段 8：原此处还有一道 canManageAutoUpdate()（需管理员或临时审批授权）。
        // 临时审批流已整体删除 —— 它并不真正授予权限（PermissionRequestService
        // 明确注释「刻意不调用 updateRoleLevel」），保留只会形成第二套权限语义。
        // 准入由上面的 canAccess（属主或管理员）负责，那是真实且可核验的边界。
        lifecycleService.updateAutoUpdate(request.getKeyId(), request.getAutoUpdate());
        return AjaxResult.success("自动更新状态修改成功", lifecycleService.findById(request.getKeyId()).orElse(null));
    }

    @PreAuthorize("isAuthenticated()")
    @DeleteMapping("/{keyId}")
    public AjaxResult revoke(@PathVariable Long keyId) {
        Keymanage current = lifecycleService.findById(keyId).orElse(null);
        if (current == null) {
            return AjaxResult.error("密钥不存在: " + keyId);
        }
        if (!canAccess(current)) {
            return AjaxResult.error("无权回收该密钥");
        }
        // Synchronous revocation — directly call service
        try {
            log.info("密钥回收: keyId={}, userId={}", keyId, getUserId());
            lifecycleService.revokeKey(keyId);
            return AjaxResult.success("密钥回收成功", keyId);
        } catch (IllegalStateException e) {
            log.warn("密钥回收失败: keyId={}, error={}", keyId, e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            log.error("密钥回收异常: keyId={}", keyId, e);
            return AjaxResult.error("密钥回收失败: " + e.getMessage());
        }
    }

    private boolean canAccess(Keymanage keymanage) {
        if (keymanage == null) {
            return false;
        }
        Long ownerId = keymanage.getUserId();
        Long currentId = getUserId();
        return SecurityUtils.isAdmin(currentId) || ownerId != null && ownerId.equals(currentId);
    }

    private String normalizeStatusQuery(String status) {
        if (status == null) {
            return null;
        }
        switch (status.trim()) {
            case "Valid":
            case "Active":
                return "0";
            case "Frozen":
                return "1";
            case "Replaced":
            case "Rotated":
                return "2";
            case "Revoked":
                return "3";
            default:
                return status.trim();
        }
    }
}
