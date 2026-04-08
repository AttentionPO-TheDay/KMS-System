package com.ruoyi.generate.mapper;

import com.ruoyi.generate.domain.SysOperLog;
import org.apache.ibatis.annotations.Mapper;

/**
 * 操作日志 数据层
 */
@Mapper
public interface SysOperLogMapper {
    /**
     * 新增操作日志
     *
     * @param operLog 操作日志对象
     */
    void insertOperlog(SysOperLog operLog);
}