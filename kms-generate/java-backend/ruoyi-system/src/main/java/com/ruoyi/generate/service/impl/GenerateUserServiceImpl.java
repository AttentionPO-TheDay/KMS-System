package com.ruoyi.generate.service.impl;

import com.ruoyi.generate.domain.GenerateUser;
import com.ruoyi.generate.mapper.GenerateUserMapper;
import com.ruoyi.generate.service.GenerateUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
public class GenerateUserServiceImpl implements GenerateUserService {

    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    @Autowired
    private GenerateUserMapper generateUserMapper;

    @Override
    public GenerateUser selectByUserName(String userName) {
        return generateUserMapper.selectByUserName(userName);
    }

    @Override
    public GenerateUser selectByUserId(Long userId) {
        return generateUserMapper.selectByUserId(userId);
    }

    @Override
    public List<GenerateUser> selectNonAdminUsers() {
        return generateUserMapper.selectNonAdminUsers();
    }

    @Override
    public int register(String userName, String rawPassword) {
        if (!StringUtils.hasText(userName) || !StringUtils.hasText(rawPassword)) {
            return 0;
        }
        if (generateUserMapper.selectByUserName(userName) != null) {
            return 0;
        }

        GenerateUser user = new GenerateUser();
        user.setUserName(userName);
        user.setNickName(userName);
        user.setPassword(passwordEncoder.encode(rawPassword));
        user.setStatus("0");
        user.setDelFlag("0");
        user.setRoleLevel(2);
        return generateUserMapper.insertUser(user);
    }

    @Override
    public boolean matchesPassword(String rawPassword, String encodedPassword) {
        return StringUtils.hasText(rawPassword)
                && StringUtils.hasText(encodedPassword)
                && passwordEncoder.matches(rawPassword, encodedPassword);
    }
}
