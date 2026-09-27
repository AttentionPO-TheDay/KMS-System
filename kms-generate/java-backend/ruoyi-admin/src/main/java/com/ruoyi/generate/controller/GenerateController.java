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
import com.ruoyi.generate.service.KeyValueSanitizer;
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
 *
 * <p>注意：原先的 {@code GET /generate/key/public-list}（公共密钥列表）已按 D1 整体删除。
 * 它允许一个用户读到其他用户的公钥集合，与「密钥不外泄」的目标冲突；
 * 其配套的整套权限申请子系统（权限项 {@code PUBLIC_KEY_LIST}）也已一并移除。
 * 用户侧现在只能查询自己的密钥（见 {@link #list(Keymanage)}）。
 *
 * <p>替换它的是 {@link #publicAssets(Keymanage)}：管理端「公钥查询」页需要一个
 * "查看全部资产"的入口（见计划 §6.2），但该入口**只对管理员开放**，
 * 且返回的 `keyValue` 只保留公钥部分、绝不带出 `partialKey` 这类私钥材料。
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
        // 列表一律不带密钥材料：已核对全部现网页面，没有任何列表消费 keyValue。
        // 需要材料的地方走的是创建/更新响应或详情接口（见 KeyValueSanitizer 的说明）。
        KeyValueSanitizer.stripMaterial(list);
        return getDataTable(list);
    }

    /**
     * 管理端「公钥查询」：查看全部用户的**公钥**资产。
     * GET /generate/key/public-assets
     *
     * <p>与已被 D1 删除的 {@code /public-list} 的区别：
     * <ul>
     *   <li>只对管理员开放（{@code role_level <= 0}），**不再是"申请即得"的临时权限**；</li>
     *   <li>返回的 {@code keyValue} 只写公钥材料，私钥分片（SM2 的 {@code partialKey}、
     *       SSCL 的 {@code SSCLEA}）与格算法的完整私钥一律不出库。</li>
     * </ul>
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/public-assets")
    public TableDataInfo publicAssets(Keymanage query) {
        ensureRoleAdmin();
        startPage();
        List<Keymanage> list = generateKeyService.selectKeyList(query);
        List<Keymanage> sanitized = new ArrayList<>();
        for (Keymanage keymanage : list) {
            String publicValue = KeyValueSanitizer.publicProjection(keymanage);
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
        boolean isOwner = keymanage.getUserId() != null && keymanage.getUserId().equals(getUserId());
        if (!isCurrentAdmin() && !isOwner) {
            return AjaxResult.error("无权访问该密钥数据");
        }
        // 管理员能看别人的密钥，但不该看到别人的密钥材料；
        // 属主本人也只在 SM2/SSCL 下才需要 key_value（客户端要据此现算 d_A）。
        KeyValueSanitizer.sanitizeDetail(keymanage, isOwner);
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

    /**
     * 按「角色等级」判定管理员（Q2 / D13：role_level &lt;= 0）。
     *
     * <p>刻意不用 {@link #isCurrentAdmin()}：那个判据等价于 RuoYi 的 {@code userId == 1}，
     * 只有超级管理员账号能满足。管理端合并后，进入管理控制台的判据已统一为
     * {@code role_level <= 0}（D9），若这里仍用 userId==1，则 level=0 的普通管理员
     * 能打开「公钥查询」页却拿不到数据，判据前后不一致。
     */
    private void ensureRoleAdmin() {
        GenerateUser currentUser = generateUserService.selectByUserId(getUserId());
        if (currentUser == null || currentUser.getRoleLevel() == null || currentUser.getRoleLevel() > 0) {
            throw new IllegalArgumentException("仅管理员可执行该操作");
        }
    }

    /**
     * 取一条密钥的**公钥**材料，取不到则返回 null。
     *
     * <p>实现已收敛到 {@link KeyValueSanitizer#publicProjection}，避免"公钥投影"的规则
     * 在多个类里各写一份、日后改一处漏一处（本方法原先就是第二份拷贝）。
     * 规则与安全要点见该类的注释。
     *
     * @deprecated 直接用 {@code KeyValueSanitizer.publicProjection(keymanage)}
     */
    @Deprecated
    private String extractPublicValue(Keymanage keymanage) {
        return KeyValueSanitizer.publicProjection(keymanage);
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
}
