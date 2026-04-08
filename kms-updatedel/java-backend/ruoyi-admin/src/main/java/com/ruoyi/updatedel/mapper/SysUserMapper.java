package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface SysUserMapper {
    SysUser selectUserById(Long userId);

    SysUser selectUserByUserName(String userName);

    int updateRoleLevel(@Param("userId") Long userId, @Param("roleLevel") Integer roleLevel);
}
