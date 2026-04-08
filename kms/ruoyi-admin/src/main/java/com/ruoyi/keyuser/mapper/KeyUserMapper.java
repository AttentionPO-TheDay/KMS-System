package com.ruoyi.keyuser.mapper;

import java.util.List;
import com.ruoyi.keyuser.domain.KeyUser;

/**
 * 用户管理Mapper接口
 * 
 * @author ruoyi
 * @date 2024-12-30
 */
public interface KeyUserMapper 
{
    /**
     * 查询用户管理
     * 
     * @param userId 用户管理主键
     * @return 用户管理
     */
    public KeyUser selectKeyUserByUserId(Long userId);

    /**
     * 查询用户管理列表
     * 
     * @param keyUser 用户管理
     * @return 用户管理集合
     */
    public List<KeyUser> selectKeyUserList(KeyUser keyUser);

    /**
     * 新增用户管理
     * 
     * @param keyUser 用户管理
     * @return 结果
     */
    public int insertKeyUser(KeyUser keyUser);

    /**
     * 修改用户管理
     * 
     * @param keyUser 用户管理
     * @return 结果
     */
    public int updateKeyUser(KeyUser keyUser);

    /**
     * 删除用户管理
     * 
     * @param userId 用户管理主键
     * @return 结果
     */
    public int deleteKeyUserByUserId(Long userId);

    /**
     * 批量删除用户管理
     * 
     * @param userIds 需要删除的数据主键集合
     * @return 结果
     */
    public int deleteKeyUserByUserIds(Long[] userIds);
}
