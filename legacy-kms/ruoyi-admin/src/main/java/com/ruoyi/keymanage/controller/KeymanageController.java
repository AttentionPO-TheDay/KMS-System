package com.ruoyi.keymanage.controller;

import java.util.List;
import javax.servlet.http.HttpServletResponse;

import com.fasterxml.jackson.core.JsonProcessingException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.ruoyi.common.annotation.Log;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.enums.BusinessType;
import com.ruoyi.keymanage.domain.Keymanage;
import com.ruoyi.keymanage.service.IKeymanageService;
import com.ruoyi.common.utils.poi.ExcelUtil;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.keymanage.domain.KeyAnalysisResultDto;
import com.ruoyi.common.utils.KeyValidator;
import com.ruoyi.common.exception.KeyValidationException;
import java.time.LocalDateTime; // 导入 LocalDateTime 类
import java.time.format.DateTimeFormatter; // 导入 DateTimeFormatter 类
import com.ruoyi.common.utils.SecurityUtils;

/**
 * 密钥管理Controller
 * 
 * @author ruoyi
 * @date 2025-01-14
 */
@RestController
@RequestMapping("/keymanage/keymanage")
public class KeymanageController extends BaseController {
    @Autowired
    private IKeymanageService keymanageService;

    /**
     * 查询密钥管理列表
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/list")
    public TableDataInfo list(Keymanage keymanage) {
        startPage();
        // 非管理员只能查看自己的密钥
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())) {
            keymanage.setUserId(SecurityUtils.getUserId());
        }
        List<Keymanage> list = keymanageService.selectkeymanageList(keymanage);
        return getDataTable(list);
    }

    /**
     * 导出密钥管理列表
     */
    @PreAuthorize("@ss.hasPermi('keymanage:keymanage:export')")
    @Log(title = "密钥管理", businessType = BusinessType.EXPORT)
    @PostMapping("/export")
    public void export(HttpServletResponse response, Keymanage keymanage) {
        List<Keymanage> list = keymanageService.selectkeymanageList(keymanage);
        ExcelUtil<Keymanage> util = new ExcelUtil<Keymanage>(Keymanage.class);
        util.exportExcel(response, list, "密钥管理数据");
    }

    /**
     * 获取密钥管理详细信息
     */
    /**
     * 获取密钥管理详细信息
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping(value = "/{keyId}")
    public AjaxResult getInfo(@PathVariable("keyId") Long keyId) {
        Keymanage keymanage = keymanageService.selectkeymanageByKeyId(keyId);
        if (keymanage == null) {
            return AjaxResult.error("密钥不存在");
        }
        // 校验归属权: 非管理员且非数据所有者
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())
                && !keymanage.getUserId().equals(SecurityUtils.getUserId())) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        return success(keymanage);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping(value = "/analysis/{keyId}")
    public AjaxResult getAnalysis(@PathVariable("keyId") Long keyId) {
        Keymanage keymanage = keymanageService.selectkeymanageByKeyId(keyId);
        if (keymanage == null) {
            return AjaxResult.error("密钥不存在");
        }
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())
                && !keymanage.getUserId().equals(SecurityUtils.getUserId())) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        try {
            KeyAnalysisResultDto analysisResult = keymanageService.getAssociationAnalysis(keyId);
            return success(analysisResult);
        } catch (Exception e) {
            return AjaxResult.error("分析获取失败: " + e.getMessage());
        }
    }

    /**
     * 获取公共参数
     */
    @PostMapping("/comparam")
    public String getComParam(@RequestBody Keymanage keymanage) throws JsonProcessingException {
        return keymanageService.getComParam(keymanage);
    }

    /**
     * 新增密钥管理
     */
    /**
     * 新增密钥管理
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥管理", businessType = BusinessType.INSERT)
    @PostMapping
    public AjaxResult add(@RequestBody Keymanage keymanage) {
        // 强制设置为当前用户ID (防止替他人创建)
        // 即使是管理员创建，逻辑上也应明确是为哪个用户创建，这里简化为谁操作算谁的，或者保留前端传值但仅限管理员
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())) {
            keymanage.setUserId(SecurityUtils.getUserId());
        } else if (keymanage.getUserId() == null) {
            // 管理员未指定则默认为管理员自己
            keymanage.setUserId(SecurityUtils.getUserId());
        }
        try {
            // 参数验证
            if ("SM2".equals(keymanage.getEncrytName()) && keymanage.getuA() != null) {
                KeyValidator.validateSM2PublicKey(keymanage.getuA());
            }
            if ("SSCL".equals(keymanage.getEncrytName()) && keymanage.getKeyDomain() != null) {
                KeyValidator.validateKeyDomain(keymanage.getKeyDomain());
            }

            LocalDateTime now = LocalDateTime.now();
            DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
            String timestamp = now.format(formatter);
            System.out.println("[" + timestamp + "] keymanage 对象内容: " + keymanage);

            return toAjax(keymanageService.insertkeymanage(keymanage));
        } catch (KeyValidationException e) {
            logger.warn("密钥参数验证失败: {}", e.getMessage());
            return AjaxResult.error(e.getMessage());
        }
    }

    /**
     * 修改密钥管理
     */
    /**
     * 修改密钥管理
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥管理", businessType = BusinessType.UPDATE)
    @PutMapping
    public AjaxResult edit(@RequestBody Keymanage keymanage) {
        // 校验归属权
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())) {
            Keymanage oldKey = keymanageService.selectkeymanageByKeyId(keymanage.getKeyId());
            if (oldKey == null || !oldKey.getUserId().equals(SecurityUtils.getUserId())) {
                return AjaxResult.error("无权修改该密钥");
            }
            // 确保不会修改userId
            keymanage.setUserId(SecurityUtils.getUserId());
        }
        return toAjax(keymanageService.updatekeymanage(keymanage));
    }

    /**
     * 删除密钥管理
     */
    /**
     * 删除密钥管理
     */
    @PreAuthorize("isAuthenticated()")
    @Log(title = "密钥管理", businessType = BusinessType.DELETE)
    @DeleteMapping("/{keyIds}")
    public AjaxResult remove(@PathVariable Long[] keyIds) {
        // 校验归属权
        if (!SecurityUtils.isAdmin(SecurityUtils.getUserId())) {
            for (Long keyId : keyIds) {
                Keymanage oldKey = keymanageService.selectkeymanageByKeyId(keyId);
                if (oldKey != null && !oldKey.getUserId().equals(SecurityUtils.getUserId())) {
                    return AjaxResult.error("无权删除密钥: " + keyId);
                }
            }
        }
        return toAjax(keymanageService.deletekeymanageByKeyIds(keyIds));
    }
}
