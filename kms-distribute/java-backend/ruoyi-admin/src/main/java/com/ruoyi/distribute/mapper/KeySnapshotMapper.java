package com.ruoyi.distribute.mapper;

import com.ruoyi.distribute.domain.Keymanage;

/**
 * 查询密钥快照，补全分发记录所需字段。
 */
public interface KeySnapshotMapper
{
    Keymanage selectKeySnapshotById(Long keyId);
}
