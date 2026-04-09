package com.ruoyi.generate.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;

/**
 * 生成记录查询控制器
 * 提供密钥生成结果的查询接口
 */
@RestController
@RequestMapping("/generate/key")
public class GenerateController extends BaseController {

    private static final Logger log = LoggerFactory.getLogger(GenerateController.class);

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private GenerateUserService generateUserService;

    /**
     * 查询生成密钥列表
     * GET /generate/key/list
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query) {
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
            query.setUserName(null);
        }
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        return getDataTable(list);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/public-list")
    public TableDataInfo publicList(Keymanage query) {
        GenerateUser currentUser = generateUserService.selectByUserId(getUserId());
        if (currentUser == null || currentUser.getRoleLevel() == null || currentUser.getRoleLevel() > 1) {
            return getDataTable(new ArrayList<>());
        }

        query.setUserId(null);
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        List<Keymanage> sanitized = new ArrayList<>();
        for (Keymanage keymanage : list) {
            String publicValue = extractPublicValue(keymanage);
            if (publicValue == null || publicValue.trim().isEmpty()) {
                continue;
            }
            Keymanage item = new Keymanage();
            item.setKeyId(keymanage.getKeyId());
            item.setUserId(keymanage.getUserId());
            item.setUserName(keymanage.getUserName());
            item.setEncrytType(keymanage.getEncrytType());
            item.setEncrytName(keymanage.getEncrytName());
            item.setKeyName(keymanage.getKeyName());
            item.setCreTime(keymanage.getCreTime());
            item.setKeyValue(publicValue);
            sanitized.add(item);
        }
        return getDataTable(sanitized);
    }

    /**
     * 查询单个密钥详情
     * GET /generate/key/{keyId}
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult getById(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        if (!isCurrentAdmin() && (keymanage.getUserId() == null || !keymanage.getUserId().equals(getUserId()))) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        return AjaxResult.success("查询成功", keymanage);
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.getLoginUser().getUser() != null && SecurityUtils.getLoginUser().getUser().isAdmin();
    }

    private String extractPublicValue(Keymanage keymanage) {
        if (keymanage == null || keymanage.getKeyValue() == null) {
            return null;
        }
        if (!"无证书非对称加密".equals(keymanage.getEncrytType())) {
            return null;
        }
        try {
            JSONObject payload = JSON.parseObject(keymanage.getKeyValue());
            if ("SM2".equals(keymanage.getEncrytName())) {
                return payload.getString("finalPublicKey");
            }
            if ("SSCL".equals(keymanage.getEncrytName())) {
                return payload.getString("SSCLKey");
            }
        } catch (Exception ex) {
            log.warn("解析公共密钥失败: keyId={}", keymanage.getKeyId(), ex);
        }
        return null;
    }
}
