package com.ruoyi.generate.service.impl;

import com.ruoyi.generate.domain.SysOperLog;
import com.ruoyi.generate.mapper.SysOperLogMapper;
import com.ruoyi.generate.service.ISysOperLogService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * 操作日志 服务层处理
 */
@Service
public class GenerateSysOperLogServiceImpl implements ISysOperLogService {
    @Autowired
    private SysOperLogMapper operLogMapper;

    /**
     * 新增操作日志
     *
     * @param operLog 操作日志对象
     */
    @Override
    public void insertOperlog(SysOperLog operLog) {
        operLogMapper.insertOperlog(operLog);
    }
}
