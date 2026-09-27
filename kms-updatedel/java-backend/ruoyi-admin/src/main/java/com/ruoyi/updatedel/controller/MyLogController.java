package com.ruoyi.updatedel.controller;

import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.page.TableDataInfo;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.domain.SysLogininfor;
import com.ruoyi.system.domain.SysOperLog;
import com.ruoyi.system.service.ISysLogininforService;
import com.ruoyi.system.service.ISysOperLogService;
import com.ruoyi.updatedel.domain.KeyOperationRecord;
import com.ruoyi.updatedel.service.KeyOperationRecordService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 「我的操作日志」（用户前台 /my-logs 页，Q8 / D14）。
 *
 * <h3>为什么单独开一组接口，而不是复用 /monitor/*</h3>
 * RuoYi 自带的 {@code /monitor/operlog} 与 {@code /monitor/logininfor} 都要求
 * {@code monitor:operlog:list} / {@code monitor:logininfor:list} 这类管理员权限，
 * 普通用户拿不到；即使放开，它们也允许调用方自行指定 {@code operName} /
 * {@code userName}，等于让任何登录用户读取他人的日志。
 *
 * <h3>本控制器的两条硬约束</h3>
 * <ol>
 *   <li><b>查询对象只由令牌决定。</b>三个接口都从
 *       {@link SecurityUtils#getUserId()} / {@link SecurityUtils#getUsername()}
 *       取值覆盖查询条件，**不接受**任何来自请求参数的用户标识，因此不存在越权读取。</li>
 *   <li><b>用户名字段用精确匹配。</b>底层 XML 里 {@code operName} / {@code userName}
 *       走的是 LIKE，会做出前缀/子串误命中（用户 {@code yx} 会读到 {@code yx2} 的记录）。
 *       故这里改用 {@code params.operNameExact} / {@code params.userNameExact}
 *       这两个等值条件，详见对应 Mapper 的注释。</li>
 * </ol>
 *
 * 日志源与 D14 的约定一致：密钥操作记录 + 系统操作日志 + 登录日志。
 */
@RestController
@RequestMapping("/lifecycle/my-logs")
public class MyLogController extends BaseController {

    private final KeyOperationRecordService keyOperationRecordService;
    private final ISysOperLogService operLogService;
    private final ISysLogininforService logininforService;

    public MyLogController(KeyOperationRecordService keyOperationRecordService,
                           ISysOperLogService operLogService,
                           ISysLogininforService logininforService) {
        this.keyOperationRecordService = keyOperationRecordService;
        this.operLogService = operLogService;
        this.logininforService = logininforService;
    }

    /**
     * 我的密钥操作记录（更新 / 回收 / 接收等），含链上信息。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/key-operations")
    public TableDataInfo keyOperations(KeyOperationRecord query) {
        // 只认令牌里的用户：即使请求里带了 userId / userName 也会被这里覆盖。
        query.setUserId(getUserId());
        query.setUserName(null);
        startPage();
        return getDataTable(keyOperationRecordService.list(query));
    }

    /**
     * 我的系统操作日志（RuoYi 记录的对本系统的接口调用）。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/operations")
    public TableDataInfo operations(SysOperLog query) {
        // 清掉请求里可能带来的模糊匹配条件，只保留服务端注入的精确条件。
        query.setOperName(null);
        query.getParams().put("operNameExact", SecurityUtils.getUsername());
        startPage();
        return getDataTable(operLogService.selectOperLogList(query));
    }

    /**
     * 我的登录日志（成功与失败都在内）。
     */
    @PreAuthorize("isAuthenticated()")
    @GetMapping("/logins")
    public TableDataInfo logins(SysLogininfor query) {
        query.setUserName(null);
        query.getParams().put("userNameExact", SecurityUtils.getUsername());
        startPage();
        return getDataTable(logininforService.selectLogininforList(query));
    }
}