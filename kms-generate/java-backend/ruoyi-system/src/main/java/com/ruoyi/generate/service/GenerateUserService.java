package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.GenerateUser;

import java.util.List;

public interface GenerateUserService {
    GenerateUser selectByUserName(String userName);

    GenerateUser selectByUserId(Long userId);

    List<GenerateUser> selectActiveUsers();

    List<GenerateUser> selectNonAdminUsers();

    int countActiveUsers();

    int register(String userName, String rawPassword);

    boolean matchesPassword(String rawPassword, String encodedPassword);
}
