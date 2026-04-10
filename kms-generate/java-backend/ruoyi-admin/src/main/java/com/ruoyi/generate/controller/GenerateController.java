package com.ruoyi.generate.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.service.IPermissionRequestService;
import com.ruoyi.generate.service.GenerateKeyService;
import com.ruoyi.generate.service.GenerateUserService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

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

    @Autowired
    private IPermissionRequestService permissionRequestService;

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
        boolean hasPermanentAccess = currentUser != null && currentUser.getRoleLevel() != null && currentUser.getRoleLevel() <= 1;
        boolean hasTemporaryAccess = permissionRequestService.hasActivePermission(getUserId(), "PUBLIC_KEY_LIST");
        if (!hasPermanentAccess && !hasTemporaryAccess) {
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

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/dashboard/summary")
    public AjaxResult dashboardSummary() {
        ensureAdmin();
        List<Keymanage> keys = generateKeyService.selectKeyList(new Keymanage());
        List<GenerateUser> users = generateUserService.selectActiveUsers();

        LocalDate today = LocalDate.now();
        List<String> labels = new ArrayList<>();
        List<Integer> sm2Series = new ArrayList<>();
        List<Integer> ssclSeries = new ArrayList<>();
        Map<String, Integer> algorithmDistribution = new LinkedHashMap<>();

        for (int i = 6; i >= 0; i--) {
            LocalDate day = today.minusDays(i);
            labels.add(day.toString());
            sm2Series.add(0);
            ssclSeries.add(0);
        }

        int totalSynced = 0;
        int todayGenerated = 0;
        int todaySynced = 0;
        for (Keymanage key : keys) {
            LocalDate keyDate = parseDate(key.getCreTime());
            if ("1".equals(key.getChainStatus())) {
                totalSynced++;
            }
            if (keyDate != null) {
                int dayIndex = (int) (today.toEpochDay() - keyDate.toEpochDay());
                if (dayIndex >= 0 && dayIndex < 7) {
                    int seriesIndex = 6 - dayIndex;
                    if ("SSCL".equalsIgnoreCase(key.getEncrytName())) {
                        ssclSeries.set(seriesIndex, ssclSeries.get(seriesIndex) + 1);
                    } else {
                        sm2Series.set(seriesIndex, sm2Series.get(seriesIndex) + 1);
                    }
                }
                if (today.equals(keyDate)) {
                    todayGenerated++;
                    if ("1".equals(key.getChainStatus())) {
                        todaySynced++;
                    }
                }
            }

            String algorithm = key.getEncrytName() == null || key.getEncrytName().trim().isEmpty() ? "未知" : key.getEncrytName().trim();
            algorithmDistribution.put(algorithm, algorithmDistribution.getOrDefault(algorithm, 0) + 1);
        }

        int todayUsers = 0;
        for (GenerateUser user : users) {
            if (today.equals(parseDate(user.getCreateTime()))) {
                todayUsers++;
            }
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("totalKeys", keys.size());
        payload.put("totalUsers", users.size());
        payload.put("todayGenerated", todayGenerated);
        payload.put("totalSynced", totalSynced);
        payload.put("todayUsers", todayUsers);
        payload.put("todaySynced", todaySynced);
        payload.put("recent7Days", buildRecentSeries(labels, sm2Series, ssclSeries));
        payload.put("algorithmDistribution", algorithmDistribution);
        return AjaxResult.success("查询成功", payload);
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

    @PreAuthorize("isAuthenticated()")
    @PostMapping("/history/manual")
    public AjaxResult addHistoryRecord(@RequestBody Keymanage keymanage) {
        try {
            ensureAdmin();
            validateHistoryRecord(keymanage);

            GenerateUser targetUser = generateUserService.selectByUserId(keymanage.getUserId());
            if (targetUser == null) {
                return AjaxResult.error("目标用户不存在");
            }

            keymanage.setUserName(targetUser.getUserName());
            keymanage.setKeyDomain(isBlank(keymanage.getKeyDomain()) ? "A" : keymanage.getKeyDomain().trim());
            keymanage.setKeyValue(isBlank(keymanage.getKeyValue()) ? buildHistoryKeyValue(keymanage) : keymanage.getKeyValue().trim());
            generateKeyService.insertHistoryRecord(keymanage);
            return AjaxResult.success("新增成功", keymanage);
        } catch (IllegalArgumentException ex) {
            return AjaxResult.error(ex.getMessage());
        }
    }

    private boolean isCurrentAdmin() {
        return SecurityUtils.getLoginUser().getUser() != null && SecurityUtils.getLoginUser().getUser().isAdmin();
    }

    private void ensureAdmin() {
        if (!isCurrentAdmin()) {
            throw new IllegalArgumentException("仅管理员可执行该操作");
        }
    }

    private Map<String, Object> buildRecentSeries(List<String> labels, List<Integer> sm2Series, List<Integer> ssclSeries) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("labels", labels);
        result.put("sm2", sm2Series);
        result.put("sscl", ssclSeries);
        return result;
    }

    private LocalDate parseDate(String value) {
        if (value == null || value.trim().isEmpty()) {
            return null;
        }
        String text = value.trim();
        if (text.length() >= 10) {
            text = text.substring(0, 10);
        }
        try {
            return LocalDate.parse(text);
        } catch (DateTimeParseException ex) {
            return null;
        }
    }

    private LocalDate parseDate(java.util.Date value) {
        if (value == null) {
            return null;
        }
        return value.toInstant().atZone(ZoneId.systemDefault()).toLocalDate();
    }

    private void validateHistoryRecord(Keymanage keymanage) {
        if (keymanage.getUserId() == null) {
            throw new IllegalArgumentException("请选择目标用户");
        }
        if (isBlank(keymanage.getEncrytType())) {
            throw new IllegalArgumentException("缺少加密算法类型");
        }
        if (isBlank(keymanage.getEncrytName())) {
            throw new IllegalArgumentException("缺少加密算法名称");
        }
        if (isBlank(keymanage.getKeyName())) {
            throw new IllegalArgumentException("缺少密钥名称");
        }
        if (isBlank(keymanage.getKeyUse())) {
            throw new IllegalArgumentException("缺少密钥用途");
        }
    }

    private String buildHistoryKeyValue(Keymanage keymanage) {
        JSONObject payload = new JSONObject();
        payload.put("algorithm", keymanage.getEncrytName());
        payload.put("source", "manual-history");
        payload.put("domain", isBlank(keymanage.getKeyDomain()) ? "A" : keymanage.getKeyDomain().trim());
        return payload.toJSONString();
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
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
