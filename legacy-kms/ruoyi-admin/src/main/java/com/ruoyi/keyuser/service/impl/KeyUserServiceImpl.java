package com.ruoyi.keyuser.service.impl;

import java.util.List;
import com.ruoyi.common.utils.DateUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import com.ruoyi.keyuser.mapper.KeyUserMapper;
import com.ruoyi.keyuser.domain.KeyUser;
import com.ruoyi.keyuser.service.IKeyUserService;

/**
 * 用户管理Service业务层处理
 * 
 * @author ruoyi
 * @date 2024-12-30
 */
@Service
public class KeyUserServiceImpl implements IKeyUserService 
{
    @Autowired
    private KeyUserMapper keyUserMapper;

    /**
     * 查询用户管理
     * 
     * @param userId 用户管理主键
     * @return 用户管理
     */
    @Override
    public KeyUser selectKeyUserByUserId(Long userId)
    {
        return keyUserMapper.selectKeyUserByUserId(userId);
    }

    /**
     * 查询用户管理列表
     * 
     * @param keyUser 用户管理
     * @return 用户管理
     */
    @Override
    public List<KeyUser> selectKeyUserList(KeyUser keyUser)
    {
        return keyUserMapper.selectKeyUserList(keyUser);
    }

    /**
     * 新增用户管理
     * 
     * @param keyUser 用户管理
     * @return 结果
     */
    @Override
    public int insertKeyUser(KeyUser keyUser)
    {
        keyUser.setCreateTime(DateUtils.getNowDate());
        return keyUserMapper.insertKeyUser(keyUser);
    }

    /**
     * 修改用户管理
     * 
     * @param keyUser 用户管理
     * @return 结果
     */
    @Override
    public int updateKeyUser(KeyUser keyUser)
    {
        keyUser.setUpdateTime(DateUtils.getNowDate());
        return keyUserMapper.updateKeyUser(keyUser);
    }

    /**
     * 批量删除用户管理
     * 
     * @param userIds 需要删除的用户管理主键
     * @return 结果
     */
    @Override
    public int deleteKeyUserByUserIds(Long[] userIds)
    {
        return keyUserMapper.deleteKeyUserByUserIds(userIds);
    }

    /**
     * 删除用户管理信息
     * 
     * @param userId 用户管理主键
     * @return 结果
     */
    @Override
    public int deleteKeyUserByUserId(Long userId)
    {
        return keyUserMapper.deleteKeyUserByUserId(userId);
    }
}
