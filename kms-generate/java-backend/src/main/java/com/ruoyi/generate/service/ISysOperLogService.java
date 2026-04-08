package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.SysOperLog;

/**
 * 操作日志 服务层
 */
public interface ISysOperLogService {
    /**
     * 新增操作日志
     *
     * @param operLog 操作日志对象
     */
    void insertOperlog(SysOperLog operLog);
}