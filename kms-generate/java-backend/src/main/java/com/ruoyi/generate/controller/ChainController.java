package com.ruoyi.generate.controller;

import com.ruoyi.generate.service.GenerateChainService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * 上链查询控制器
 * 提供密钥上链状态的查询接口
 */
@RestController
@RequestMapping("/generate/key/chain")
public class ChainController {

    private static final Logger log = LoggerFactory.getLogger(ChainController.class);

    @Autowired
    private GenerateChainService generateChainService;

    /**
     * 查询密钥上链状态
     * GET /generate/key/chain/{keyId}
     */
    @GetMapping("/{keyId}")
    public ResponseEntity<Map<String, Object>> getChainStatus(@PathVariable Long keyId) {
        GenerateChainService.ChainSyncStatus status = generateChainService.getChainStatus(keyId);

        Map<String, Object> result = new HashMap<>();
        if (status == null) {
            result.put("code", 404);
            result.put("msg", "密钥不存在");
            return ResponseEntity.status(404).body(result);
        }

        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", status);

        return ResponseEntity.ok(result);
    }

    /**
     * 批量查询上链状态
     * POST /generate/key/chain/batch
     */
    @PostMapping("/batch")
    public ResponseEntity<Map<String, Object>> batchGetChainStatus(@RequestBody Map<String, Object> request) {
        Object keyIdsObj = request.get("keyIds");
        if (keyIdsObj == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("code", 400);
            error.put("msg", "keyIds 参数不能为空");
            return ResponseEntity.badRequest().body(error);
        }

        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", new HashMap<>());

        return ResponseEntity.ok(result);
    }
}
