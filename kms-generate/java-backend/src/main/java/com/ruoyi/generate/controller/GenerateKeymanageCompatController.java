package com.ruoyi.generate.controller;

import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/generate/keymanage")
public class GenerateKeymanageCompatController {

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private GenerateUserService generateUserService;

    @GetMapping("/list")
    public ResponseEntity<Map<String, Object>> list(Keymanage query,
                                                    @RequestParam(defaultValue = "1") int pageNum,
                                                    @RequestParam(defaultValue = "10") int pageSize) {
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "查询成功");
        result.put("rows", list);
        result.put("data", list);
        result.put("total", list.size());
        result.put("pageNum", pageNum);
        result.put("pageSize", pageSize);
        return ResponseEntity.ok(result);
    }

    @GetMapping("/{keyId}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long keyId) {
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

    @PostMapping("/comparam")
    public ResponseEntity<Map<String, Object>> getComParam(@RequestBody Keymanage keymanage) {
        ComParam comParam = generateKeyService.getComParam(keymanage.getEncrytType(), keymanage.getEncrytName());
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "操作成功");
        result.put("data", comParam == null ? new HashMap<>() : comParam.toMap());
        return ResponseEntity.ok(result);
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> add(@RequestBody Keymanage keymanage) {
        fillUserInfo(keymanage);
        int rows = generateKeyService.insertKey(keymanage);
        Map<String, Object> result = new HashMap<>();
        result.put("code", rows > 0 ? 200 : 500);
        result.put("msg", rows > 0 ? "操作成功" : "生成失败");
        if (rows > 0) {
            result.put("data", keymanage);
        }
        return ResponseEntity.ok(result);
    }

    @PutMapping
    public ResponseEntity<Map<String, Object>> edit(@RequestBody Keymanage keymanage) {
        fillUserInfo(keymanage);
        int rows = generateKeyService.updateKey(keymanage);
        Map<String, Object> result = new HashMap<>();
        result.put("code", rows > 0 ? 200 : 500);
        result.put("msg", rows > 0 ? "操作成功" : "修改失败");
        if (rows > 0) {
            result.put("data", keymanage);
        }
        return ResponseEntity.ok(result);
    }

    @DeleteMapping("/{keyId}")
    public ResponseEntity<Map<String, Object>> remove(@PathVariable Long keyId) {
        int rows = generateKeyService.deleteKey(keyId);
        Map<String, Object> result = new HashMap<>();
        result.put("code", rows > 0 ? 200 : 500);
        result.put("msg", rows > 0 ? "操作成功" : "删除失败");
        return ResponseEntity.ok(result);
    }

    private void fillUserInfo(Keymanage keymanage) {
        if (keymanage.getUserId() != null && (keymanage.getUserName() == null || keymanage.getUserName().trim().isEmpty())) {
            GenerateUser user = generateUserService.selectByUserId(keymanage.getUserId());
            if (user != null) {
                keymanage.setUserName(user.getUserName());
            }
        }
    }
}
