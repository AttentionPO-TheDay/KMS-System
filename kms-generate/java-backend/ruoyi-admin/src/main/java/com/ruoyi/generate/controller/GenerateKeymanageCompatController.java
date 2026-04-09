package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.client.GoBackendClient;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
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

/**
 * 密钥生成兼容控制器
 *
 * 生成流程：
 * 1. 前端 → POST /generate/keymanage（Java，已 Session 鉴权）
 * 2. Java 绑定当前登录用户 → 调用 GoBackendClient
 * 3. Go 验证 X-Internal-Token → 执行密码学计算 → 发 Kafka
 * 4. Java Kafka Consumer 统一落库，控制器只返回结果快照
 */
@RestController
@RequestMapping("/generate/keymanage")
public class GenerateKeymanageCompatController extends BaseController {

    private static final Logger log = LoggerFactory.getLogger(GenerateKeymanageCompatController.class);

    @Autowired
    private GenerateKeyService generateKeyService;

    @Autowired
    private GenerateUserService generateUserService;

    @Autowired
    private GoBackendClient goBackendClient;

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage query,
                              @RequestParam(defaultValue = "1") int pageNum,
                              @RequestParam(defaultValue = "10") int pageSize) {
        bindSelfScope(query);
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        return getDataTable(list);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/{keyId}")
    public AjaxResult get(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        if (!canAccess(keymanage)) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        return AjaxResult.success("查询成功", keymanage);
    }

    @PreAuthorize("isAuthenticated()")
    @PostMapping("/comparam")
    public AjaxResult getComParam(@RequestBody Keymanage keymanage) {
        ComParam comParam = generateKeyService.getComParam(keymanage.getEncrytType(), keymanage.getEncrytName());
        return AjaxResult.success("操作成功", comParam == null ? new HashMap<>() : comParam.toMap());
    }

    /**
     * 密钥生成：Java 只负责鉴权和转发，落库统一由 Kafka Consumer 处理
     */
    @PreAuthorize("isAuthenticated()")
    @PostMapping
    public AjaxResult add(@RequestBody Keymanage keymanage) {
        try {
            fillCurrentUserInfo(keymanage);
            String keyValue = goBackendClient.enrollKey(keymanage);
            keymanage.setKeyValue(keyValue);
            return AjaxResult.success("生成请求已提交，正在后台入库", keymanage);
        } catch (Exception e) {
            log.error("密钥生成失败: userName={}, encrytName={}, error={}",
                    keymanage.getUserName(), keymanage.getEncrytName(), e.getMessage(), e);
            return error("密钥生成失败：" + e.getMessage());
        }
    }

    /**
     * 密钥更新/轮换：生成新的密钥材料并通过 Kafka 异步落库
     */
    @PreAuthorize("isAuthenticated()")
    @PutMapping
    public AjaxResult edit(@RequestBody Keymanage keymanage) {
        try {
            Keymanage oldKey = requireOwnedKey(keymanage.getKeyId());
            if (oldKey == null) {
                return AjaxResult.error("密钥不存在");
            }

            Keymanage reenrollRequest = buildReenrollRequest(oldKey, keymanage);
            String keyValue = goBackendClient.reenrollKey(reenrollRequest);
            reenrollRequest.setKeyValue(keyValue);
            return AjaxResult.success("更新请求已提交，正在后台入库", reenrollRequest);
        } catch (Exception e) {
            log.error("密钥更新失败: keyId={}, error={}", keymanage.getKeyId(), e.getMessage(), e);
            return error("密钥更新失败：" + e.getMessage());
        }
    }

    @PreAuthorize("isAuthenticated()")
    @DeleteMapping("/{keyId}")
    public AjaxResult remove(@PathVariable Long keyId) {
        Keymanage oldKey = requireOwnedKey(keyId);
        if (oldKey == null) {
            return AjaxResult.error("密钥不存在");
        }
        int rows = generateKeyService.deleteKey(keyId);
        return rows > 0 ? success() : error("删除失败");
    }

    private void fillCurrentUserInfo(Keymanage keymanage) {
        if (isCurrentAdmin() && keymanage.getUserId() != null) {
            GenerateUser targetUser = generateUserService.selectByUserId(keymanage.getUserId());
            if (targetUser == null) {
                throw new IllegalArgumentException("目标用户不存在");
            }
            keymanage.setUserName(targetUser.getUserName());
        } else {
            keymanage.setUserId(getUserId());
            keymanage.setUserName(getUsername());
        }
        if (keymanage.getAutoUpdate() == null || keymanage.getAutoUpdate().trim().isEmpty()) {
            keymanage.setAutoUpdate("false");
        }
        if (keymanage.getKeyDomain() == null || keymanage.getKeyDomain().trim().isEmpty()) {
            keymanage.setKeyDomain("A");
        }
    }

    private void bindSelfScope(Keymanage query) {
        if (!isCurrentAdmin()) {
            query.setUserId(getUserId());
            query.setUserName(null);
        }
    }

    private Keymanage requireOwnedKey(Long keyId) {
        if (keyId == null) {
            throw new IllegalArgumentException("缺少密钥ID");
        }
        Keymanage oldKey = generateKeyService.selectKeyById(keyId);
        if (oldKey == null) {
            return null;
        }
        if (!canAccess(oldKey)) {
            throw new IllegalArgumentException("无权操作该密钥");
        }
        return oldKey;
    }

    private boolean canAccess(Keymanage keymanage) {
        return isCurrentAdmin() || keymanage.getUserId() != null && keymanage.getUserId().equals(getUserId());
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.getLoginUser().getUser() != null && SecurityUtils.getLoginUser().getUser().isAdmin();
    }

    private Keymanage buildReenrollRequest(Keymanage oldKey, Keymanage incoming) {
        Keymanage request = new Keymanage();
        request.setUserId(oldKey.getUserId());
        request.setUserName(oldKey.getUserName());
        request.setEncrytType(defaultIfBlank(incoming.getEncrytType(), oldKey.getEncrytType()));
        request.setEncrytName(defaultIfBlank(incoming.getEncrytName(), oldKey.getEncrytName()));
        request.setKeyName(defaultIfBlank(incoming.getKeyName(), oldKey.getKeyName()));
        request.setKeyUse(defaultIfBlank(incoming.getKeyUse(), oldKey.getKeyUse()));
        request.setuA(defaultIfBlank(incoming.getuA(), oldKey.getuA()));
        request.setKeyDomain(defaultIfBlank(incoming.getKeyDomain(), oldKey.getKeyDomain()));
        request.setAutoUpdate(defaultIfBlank(incoming.getAutoUpdate(), oldKey.getAutoUpdate()));
        if (request.getKeyDomain() == null || request.getKeyDomain().trim().isEmpty()) {
            request.setKeyDomain("A");
        }
        return request;
    }

    private String defaultIfBlank(String value, String fallback) {
        return value == null || value.trim().isEmpty() ? fallback : value;
    }
}
