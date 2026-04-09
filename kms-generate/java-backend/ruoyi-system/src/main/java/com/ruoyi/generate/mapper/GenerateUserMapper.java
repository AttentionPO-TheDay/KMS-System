package com.ruoyi.generate.mapper;

import com.ruoyi.generate.domain.GenerateUser;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface GenerateUserMapper {
    GenerateUser selectByUserName(String userName);

    GenerateUser selectByUserId(Long userId);

    List<GenerateUser> selectActiveUsers();

    List<GenerateUser> selectNonAdminUsers();

    int countActiveUsers();

    int insertUser(GenerateUser user);
}
