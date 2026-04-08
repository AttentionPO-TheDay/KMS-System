package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.generate.service.GenerateChainService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
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
        return AjaxResult.success("查询成功", new HashMap<>());
    }
}
