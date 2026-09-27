package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateChainService;
import com.ruoyi.generate.service.GenerateKeyService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 上链查询控制器
 * 提供密钥上链状态的查询接口
 *
 * 安全说明：链上状态按密钥归属鉴权，非管理员只能查询自己的密钥，
 * 避免跨租户读取他人存证信息（上链哈希、区块高度）。
 */
@RestController
@RequestMapping("/generate/key/chain")
public class ChainController extends BaseController {

    private static final Logger log = LoggerFactory.getLogger(ChainController.class);

    @Autowired
    private GenerateChainService generateChainService;

    @Autowired
    private GenerateKeyService generateKeyService;

    /**
     * 查询密钥上链状态
     * GET /generate/key/chain/{keyId}
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult getChainStatus(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        if (!canAccess(keymanage)) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        GenerateChainService.ChainSyncStatus status = generateChainService.getChainStatus(keyId);
        if (status == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        return AjaxResult.success("查询成功", status);
    }

    /**
     * 批量查询上链状态
     * POST /generate/key/chain/batch
     *
     * 无权限的 keyId 会被静默跳过，不泄露其是否存在。
     */
    @PreAuthorize("isAuthenticated()")
    @PostMapping("/batch")
    public AjaxResult batchGetChainStatus(@RequestBody Map<String, Object> request) {
        Object keyIdsObj = request.get("keyIds");
        if (keyIdsObj == null) {
            return error("keyIds 参数不能为空");
        }

        List<Long> keyIds = parseKeyIds(keyIdsObj);
        if (keyIds.isEmpty()) {
            return error("keyIds 参数不能为空");
        }

        Map<Long, GenerateChainService.ChainSyncStatus> result = new LinkedHashMap<>();
        int skipped = 0;
        for (Long keyId : keyIds) {
            if (keyId == null) {
                continue;
            }
            Keymanage keymanage = generateKeyService.selectKeyById(keyId);
            if (keymanage == null || !canAccess(keymanage)) {
                skipped++;
                continue;
            }
            result.put(keyId, generateChainService.getChainStatus(keyId));
        }
        if (skipped > 0) {
            log.debug("批量链上查询跳过 {} 个无权限或不存在 key", skipped);
        }
        return AjaxResult.success("查询成功", result);
    }

    /**
     * 与 GenerateKeymanageCompatController 保持一致的归属判据：
     * 管理员放行，否则要求密钥归属当前登录用户。
     */
    private boolean canAccess(Keymanage keymanage) {
        if (isCurrentAdmin()) {
            return true;
        }
        Long ownerId = keymanage.getUserId();
        Long currentId = getUserId();
        return ownerId != null && ownerId.equals(currentId);
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

    private List<Long> parseKeyIds(Object keyIdsObj) {
        List<Long> keyIds = new ArrayList<>();
        if (keyIdsObj instanceof Collection) {
            for (Object item : (Collection<?>) keyIdsObj) {
                Long keyId = toLong(item);
                if (keyId != null) {
                    keyIds.add(keyId);
                }
            }
            return keyIds;
        }

        if (keyIdsObj instanceof String) {
            String[] parts = ((String) keyIdsObj).split(",");
            for (String part : parts) {
                Long keyId = toLong(part);
                if (keyId != null) {
                    keyIds.add(keyId);
                }
            }
        }
        return keyIds;
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        try {
            String text = String.valueOf(value).trim();
            if (text.isEmpty()) {
                return null;
            }
            return Long.valueOf(text);
        } catch (NumberFormatException ex) {
            log.warn("忽略非法 keyId: {}", value);
            return null;
        }
    }
}
