package com.ruoyi.generate.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.generate.client.GoBackendClient;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
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
 * 2. Java 填充用户信息 → 调用 GoBackendClient.enrollKey()
 * 3. Go 验证 X-Internal-Token → 执行密码学计算 → 发 Kafka
 * 4. Java 拿到 Go 返回的 keyValue 直接写库 → 返回前端
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

    @GetMapping("/list")
    public TableDataInfo list(Keymanage query,
                              @RequestParam(defaultValue = "1") int pageNum,
                              @RequestParam(defaultValue = "10") int pageSize) {
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        return getDataTable(list);
    }

    @GetMapping("/{keyId}")
    public AjaxResult get(@PathVariable Long keyId) {
        Keymanage keymanage = generateKeyService.selectKeyById(keyId);
        if (keymanage == null) {
            return AjaxResult.error(404, "密钥不存在");
        }
        return AjaxResult.success("查询成功", keymanage);
    }

    @PostMapping("/comparam")
    public AjaxResult getComParam(@RequestBody Keymanage keymanage) {
        ComParam comParam = generateKeyService.getComParam(keymanage.getEncrytType(), keymanage.getEncrytName());
        return AjaxResult.success("操作成功", comParam == null ? new HashMap<>() : comParam.toMap());
    }

    /**
     * 密钥生成：调用 Go 高性能服务执行密码学计算，拿到 keyValue 后写库
     */
    @PostMapping
    public AjaxResult add(@RequestBody Keymanage keymanage) {
        try {
            fillUserInfo(keymanage);
            // 1. 调用 Go 服务（携带 X-Internal-Token），Go 执行密码学计算并异步发 Kafka
            String keyValue = goBackendClient.enrollKey(keymanage);
            // 2. 将 Go 返回的 keyValue 写入对象，Java 直接同步落库（保证接口立即返回数据）
            keymanage.setKeyValue(keyValue);
            int rows = generateKeyService.insertKey(keymanage);
            if (rows > 0) {
                return AjaxResult.success("操作成功", keymanage);
            }
            return error("生成失败：数据库写入异常");
        } catch (Exception e) {
            log.error("密钥生成失败: userName={}, encrytName={}, error={}",
                    keymanage.getUserName(), keymanage.getEncrytName(), e.getMessage(), e);
            return error("密钥生成失败：" + e.getMessage());
        }
    }

    /**
     * 密钥更新/轮换：调用 Go 重新生成密钥材料再写库
     */
    @PutMapping
    public AjaxResult edit(@RequestBody Keymanage keymanage) {
        try {
            fillUserInfo(keymanage);
            if (needRegenerate(keymanage)) {
                String keyValue = goBackendClient.enrollKey(keymanage);
                keymanage.setKeyValue(keyValue);
            }
            int rows = generateKeyService.updateKey(keymanage);
            if (rows > 0) {
                return AjaxResult.success("操作成功", keymanage);
            }
            return error("修改失败：数据库写入异常");
        } catch (Exception e) {
            log.error("密钥更新失败: keyId={}, error={}", keymanage.getKeyId(), e.getMessage(), e);
            return error("密钥更新失败：" + e.getMessage());
        }
    }

    @DeleteMapping("/{keyId}")
    public AjaxResult remove(@PathVariable Long keyId) {
        int rows = generateKeyService.deleteKey(keyId);
        return rows > 0 ? success() : error("删除失败");
    }

    /**
     * 填充用户信息（userName）
     */
    private void fillUserInfo(Keymanage keymanage) {
        if (keymanage.getUserId() != null
                && (keymanage.getUserName() == null || keymanage.getUserName().trim().isEmpty())) {
            GenerateUser user = generateUserService.selectByUserId(keymanage.getUserId());
            if (user != null) {
                keymanage.setUserName(user.getUserName());
            }
        }
    }

    /**
     * 判断此次更新是否需要重新生成密钥材料
     * 无证书非对称加密（SM2/SSCL）和对称加密（AES）都需要重新生成
     */
    private boolean needRegenerate(Keymanage keymanage) {
        String encrytType = keymanage.getEncrytType();
        if (encrytType == null) {
            Keymanage old = generateKeyService.selectKeyById(keymanage.getKeyId());
            if (old != null) {
                encrytType = old.getEncrytType();
                if (keymanage.getEncrytName() == null) keymanage.setEncrytName(old.getEncrytName());
                if (keymanage.getUserName() == null)   keymanage.setUserName(old.getUserName());
                if (keymanage.getuA() == null)         keymanage.setuA(old.getuA());
                if (keymanage.getKeyDomain() == null)  keymanage.setKeyDomain(old.getKeyDomain());
                keymanage.setEncrytType(encrytType);
            }
        }
        return "无证书非对称加密".equals(encrytType) || "对称加密".equals(encrytType);
    }
}
