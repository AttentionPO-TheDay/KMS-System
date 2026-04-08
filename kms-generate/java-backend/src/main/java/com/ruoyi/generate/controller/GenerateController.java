package com.ruoyi.generate.controller;

import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 生成记录查询控制器
 * 提供密钥生成结果的查询接口
 */
@RestController
@RequestMapping("/generate/key")
public class GenerateController {

    private static final Logger log = LoggerFactory.getLogger(GenerateController.class);

    @Autowired
    private GenerateKeyService generateKeyService;

    /**
     * 查询生成密钥列表
     * GET /generate/key/list
     */
    @GetMapping("/list")
    public ResponseEntity<Map<String, Object>> list(
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String userName,
            @RequestParam(required = false) String encrytType,
            @RequestParam(required = false) String encrytName,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String chainStatus,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize) {

        Keymanage query = new Keymanage();
        query.setUserId(userId);
        query.setUserName(userName);
        query.setEncrytType(encrytType);
        query.setEncrytName(encrytName);
        query.setStatus(status);
        query.setChainStatus(chainStatus);

        List<Keymanage> list = generateKeyService.selectKeyList(query);

        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", list);
        result.put("rows", list);
        result.put("total", list.size());
        result.put("pageNum", pageNum);
        result.put("pageSize", pageSize);

        return ResponseEntity.ok(result);
    }

    /**
     * 查询单个密钥详情
     * GET /generate/key/{keyId}
     */
    @GetMapping("/{keyId}")
    public ResponseEntity<Map<String, Object>> getById(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);

        Map<String, Object> result = new HashMap<>();
        if (keymanage == null) {
            result.put("code", 404);
            result.put("msg", "密钥不存在");
            return ResponseEntity.status(404).body(result);
        }

        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("data", keymanage);

        return ResponseEntity.ok(result);
    }
}
