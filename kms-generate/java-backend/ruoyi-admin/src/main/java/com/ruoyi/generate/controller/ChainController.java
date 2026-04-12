package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.generate.service.GenerateChainService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 上链查询控制器
 * 提供密钥上链状态的查询接口
 */
@RestController
@RequestMapping("/generate/key/chain")
public class ChainController extends BaseController {

    private static final Logger log = LoggerFactory.getLogger(ChainController.class);

    @Autowired
    private GenerateChainService generateChainService;

    /**
     * 查询密钥上链状态
     * GET /generate/key/chain/{keyId}
     */
    @GetMapping("/{keyId}")
    public AjaxResult getChainStatus(@PathVariable Long keyId) {
        GenerateChainService.ChainSyncStatus status = generateChainService.getChainStatus(keyId);
        if (status == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        return AjaxResult.success("查询成功", status);
    }

    /**
     * 批量查询上链状态
     * POST /generate/key/chain/batch
     */
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
        for (Long keyId : keyIds) {
            if (keyId == null) {
                continue;
            }
            result.put(keyId, generateChainService.getChainStatus(keyId));
        }
        return AjaxResult.success("查询成功", result);
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
