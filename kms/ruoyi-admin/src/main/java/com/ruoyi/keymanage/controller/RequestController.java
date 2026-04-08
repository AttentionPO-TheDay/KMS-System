package com.ruoyi.keymanage.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.KeyValidator;
import com.ruoyi.common.exception.KeyValidationException;
import com.ruoyi.keymanage.domain.Keymanage;
import com.ruoyi.keymanage.domain.KeyStatus;
import com.ruoyi.keymanage.service.IKeymanageService;
import com.ruoyi.keymanage.service.RequestConsumer;
import com.ruoyi.keymanage.service.Requestor;
import com.ruoyi.keyuser.domain.KeyUser;
import com.ruoyi.keyuser.service.IKeyUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import javax.servlet.http.HttpServletRequest;
import com.fasterxml.jackson.core.JsonProcessingException;
import java.util.Date;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/keymanage/request")
public class RequestController extends BaseController {
    @Autowired
    private RequestConsumer requestConsumer;
    @Autowired
    private IKeymanageService keymanageService;
    @Autowired
    private IKeyUserService keyUserService;

    @PostMapping("/Register")
    public AjaxResult register(
            @RequestBody Map<String, Object> params,
            HttpServletRequest request // 变量名改简洁点
    ) {
        try {
            // 1. 获取参数
            String user = (String) params.get("user");
            String password = (String) params.get("password");

            if (user == null || password == null) {
                return AjaxResult.error("用户名或密码不能为空");
            }

            // 2. 参数验证
            try {
                KeyValidator.validateCredentials(user, password);
            } catch (KeyValidationException e) {
                return AjaxResult.error(e.getMessage());
            }

            // 2. 日志记录 (Ruoyi 自带的 startPage/Log 可能会冲突，手动打印建议保留核心信息)
            // 这里的 Date 转换逻辑没问题，但可以简化
            System.out.println("[Register Request] User: " + user + ", IP: " + request.getRemoteAddr());

            // 3. 构建查重条件 (只查用户名！)
            KeyUser keyUserSelect = new KeyUser();
            keyUserSelect.setUserName(user);

            // 4. 【优化】只查一次数据库
            List<KeyUser> existingUsers = keyUserService.selectKeyUserList(keyUserSelect);

            // 5. 判断是否存在
            if (existingUsers == null || existingUsers.isEmpty()) {
                // 不存在，执行插入
                KeyUser newUser = new KeyUser();
                newUser.setUserName(user);
                newUser.setNickName(user); // 插入时再设昵称
                newUser.setPassword(SecurityUtils.encryptPassword(password));
                newUser.setLoginIp(request.getRemoteAddr());
                newUser.setLoginDate(new Date()); // 直接 new Date() 即可，不用转 Zone

                // 补充 Ruoyi 常见必填字段 (视你的表结构而定)
                newUser.setStatus("0"); // 启用
                newUser.setDelFlag("0"); // 未删除

                return toAjax(keyUserService.insertKeyUser(newUser));
            } else {
                return AjaxResult.error("注册失败: 已包含该用户");
            }

        } catch (KeyValidationException e) {
            logger.warn("注册参数验证失败: {}", e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            logger.error("注册过程发生异常", e);
            return AjaxResult.error("注册失败: 系统内部错误");
        }
    }

    @PostMapping("/ENROLL_KEY")
    public AjaxResult enroll(
            @RequestBody Map<String, Object> params) {
        try {
            String user = (String) params.get("user");
            String password = (String) params.get("password");
            String encrytType = (String) params.get("encryt_type");
            String encrytName = (String) params.get("encryt_name");
            String uA = (String) params.get("ua");

            if (user == null || password == null || encrytName == null) {
                return AjaxResult.error("信息缺失(user或password或encryt_name)");
            }
            if (uA == null || uA.equals("")) {
                return AjaxResult.error("信息缺失(用户部分公钥)");
            }

            // 参数验证
            try {
                KeyValidator.validateCredentials(user, password);
                // 如果是SM2算法，验证用户部分公钥
                if ("SM2".equals(encrytName)) {
                    KeyValidator.validateSM2PublicKey(uA);
                }
            } catch (KeyValidationException e) {
                return AjaxResult.error(e.getMessage());
            }

            LocalDateTime now = LocalDateTime.now();
            DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
            String timestamp = now.format(formatter);

            System.out.println("[" + timestamp + "] request 内容: " + "ENROLL_KEY-" + user + "-" + encrytName);

            Requestor.PasswordRequestor requestor = requestConsumer.getPasswordRequestorByUser(user);
            boolean authorized = requestor != null && requestor.authenticate(password);
            System.out.println(authorized);
            if (authorized) {

                KeyUser keyUserSelect = new KeyUser();
                keyUserSelect.setUserName(user);
                keyUserSelect.setNickName(user);
                List<KeyUser> keyUserList = keyUserService.selectKeyUserList(keyUserSelect);
                KeyUser keyUser = keyUserList.get(0);
                Long userId = keyUser.getUserId();

                Keymanage keymanage = new Keymanage();
                keymanage.setCreTime(timestamp);
                keymanage.setUpdTime(timestamp);
                keymanage.setUserName(user);
                System.out.println(encrytType);
                keymanage.setEncrytType(encrytType);
                keymanage.setEncrytName(encrytName);
                keymanage.setuA(uA);
                keymanage.setAutoUpdate("false");
                keymanage.setStatus("0"); // 这里可以加一个枚举元素
                keymanage.setKeyName("example");
                keymanage.setKeyUse("加解密");
                keymanage.setUserId(userId);

                if (keymanageService.insertkeymanage(keymanage) != 0) {
                    List<Keymanage> keymanageList = keymanageService.selectkeymanageList(keymanage);
                    Keymanage keymanageselect = keymanageList.get(0);
                    String data = keymanageselect.getKeyValue();
                    return AjaxResult.success(data);
                } else {
                    return AjaxResult.error("密钥生成失败");
                }

            } else {
                return AjaxResult.error("用户不存在或密码错误");
            }
        } catch (KeyValidationException e) {
            logger.warn("密钥生成参数验证失败: {}", e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            logger.error("密钥生成过程发生异常", e);
            return AjaxResult.error("密钥生成失败: 系统内部错误");
        }
    }

    @PostMapping("/REENROLL_KEY")
    public AjaxResult reenroll(
            @RequestParam(required = true) String user,
            @RequestParam(required = true) String password,
            @RequestParam(required = true) String encrytName) {
        LocalDateTime now = LocalDateTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        String timestamp = now.format(formatter);

        System.out.println("[" + timestamp + "] request 内容: " + "REENROLL_KEY-" + user + "-" + encrytName);

        return toAjax(1);
    }

    @PostMapping("/UPDATE_KEY")
    public AjaxResult update(@RequestBody Map<String, Object> params) {
        try {
            // 1. 获取参数
            String keyIdStr = params.get("keyid") != null ? params.get("keyid").toString() : null;
            String password = (String) params.get("password");
            String user = (String) params.get("user");

            // 2. 参数验证
            if (keyIdStr == null || password == null || user == null) {
                return AjaxResult.error("信息缺失(keyid或password或user)");
            }

            Long keyId;
            try {
                keyId = Long.parseLong(keyIdStr);
            } catch (NumberFormatException e) {
                return AjaxResult.error("keyid格式错误，必须为数字");
            }

            try {
                KeyValidator.validateCredentials(user, password);
            } catch (KeyValidationException e) {
                return AjaxResult.error(e.getMessage());
            }

            LocalDateTime now = LocalDateTime.now();
            DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
            String timestamp = now.format(formatter);

            System.out.println("[" + timestamp + "] request 内容: UPDATE_KEY-" + user + "-" + keyId);

            // 3. 用户认证
            Requestor.PasswordRequestor requestor = requestConsumer.getPasswordRequestorByUser(user);
            boolean authorized = requestor != null && requestor.authenticate(password);

            if (!authorized) {
                return AjaxResult.error("用户不存在或密码错误");
            }

            // 4. 查询密钥是否存在
            Keymanage oldKey = keymanageService.selectkeymanageByKeyId(keyId);
            if (oldKey == null) {
                return AjaxResult.error("密钥不存在: " + keyId);
            }

            // 5. 验证密钥归属权
            if (!oldKey.getUserName().equals(user)) {
                return AjaxResult.error("无权更新该密钥");
            }

            // 6. 检查密钥状态（已回收的不能更新）
            if (KeyStatus.REVOKED.getCode().equals(oldKey.getStatus())) {
                return AjaxResult.error("该密钥已被回收，无法更新");
            }

            // 7. 执行密钥轮换
            Keymanage updateKey = new Keymanage();
            updateKey.setKeyId(keyId);
            updateKey.setUpdTime(timestamp);
            // 直接从数据库获取用户部分公钥
            updateKey.setuA(oldKey.getuA());
            updateKey.setKeyDomain(oldKey.getKeyDomain());
            updateKey.setEncrytType(oldKey.getEncrytType());
            updateKey.setEncrytName(oldKey.getEncrytName());
            updateKey.setUserName(oldKey.getUserName());
            updateKey.setUserId(oldKey.getUserId());

            int result = keymanageService.updatekeymanage(updateKey);

            if (result > 0) {
                // 返回更新后的密钥信息
                Keymanage updatedKey = keymanageService.selectkeymanageByKeyId(keyId);
                return AjaxResult.success("密钥更新成功", updatedKey.getKeyValue());
            } else {
                return AjaxResult.error("密钥更新失败");
            }

        } catch (KeyValidationException e) {
            logger.warn("密钥更新参数验证失败: {}", e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            logger.error("密钥更新过程发生异常", e);
            return AjaxResult.error("密钥更新失败: 系统内部错误");
        }
    }

    @PostMapping("/UNSUSPEND_KEY")
    public AjaxResult unsuspend(
            @RequestParam(required = true) String keyid,
            @RequestParam(required = true) String password,
            @RequestParam String user) {
        LocalDateTime now = LocalDateTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        String timestamp = now.format(formatter);

        System.out.println("[" + timestamp + "] request 内容: " + "UPDATE_KEY-" + user + "-" + keyid);

        return toAjax(1);
    }

    @PostMapping("/REVOKE_KEY")
    public AjaxResult revoke(@RequestBody Map<String, Object> params) {
        try {
            // 1. 获取参数
            String keyIdStr = params.get("keyid") != null ? params.get("keyid").toString() : null;
            String password = (String) params.get("password");
            String user = (String) params.get("user");

            // 2. 参数验证
            if (keyIdStr == null || password == null || user == null) {
                return AjaxResult.error("信息缺失(keyid或password或user)");
            }

            Long keyId;
            try {
                keyId = Long.parseLong(keyIdStr);
            } catch (NumberFormatException e) {
                return AjaxResult.error("keyid格式错误，必须为数字");
            }

            try {
                KeyValidator.validateCredentials(user, password);
            } catch (KeyValidationException e) {
                return AjaxResult.error(e.getMessage());
            }

            LocalDateTime now = LocalDateTime.now();
            DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
            String timestamp = now.format(formatter);

            System.out.println("[" + timestamp + "] request 内容: REVOKE_KEY-" + user + "-" + keyId);

            // 3. 用户认证
            Requestor.PasswordRequestor requestor = requestConsumer.getPasswordRequestorByUser(user);
            boolean authorized = requestor != null && requestor.authenticate(password);

            if (!authorized) {
                return AjaxResult.error("用户不存在或密码错误");
            }

            // 4. 查询密钥是否存在
            Keymanage oldKey = keymanageService.selectkeymanageByKeyId(keyId);
            if (oldKey == null) {
                return AjaxResult.error("密钥不存在: " + keyId);
            }

            // 5. 验证密钥归属权
            if (!oldKey.getUserName().equals(user)) {
                return AjaxResult.error("无权回收该密钥");
            }

            // 6. 检查密钥状态（已回收的不能再次回收）
            if (KeyStatus.REVOKED.getCode().equals(oldKey.getStatus())) {
                return AjaxResult.error("该密钥已被回收");
            }

            // 7. 执行密钥回收（逻辑删除）
            int result = keymanageService.deletekeymanageByKeyId(keyId);

            if (result > 0) {
                return AjaxResult.success("密钥回收成功", keyId);
            } else {
                return AjaxResult.error("密钥回收失败");
            }

        } catch (KeyValidationException e) {
            logger.warn("密钥回收参数验证失败: {}", e.getMessage());
            return AjaxResult.error(e.getMessage());
        } catch (Exception e) {
            logger.error("密钥回收过程发生异常", e);
            return AjaxResult.error("密钥回收失败: 系统内部错误");
        }
    }

    /**
     * 获取公共参数
     */
    @PostMapping("/comparam")
    public String getComParam(@RequestBody Keymanage keymanage) throws JsonProcessingException {
        return keymanageService.getComParam(keymanage);
    }
}
