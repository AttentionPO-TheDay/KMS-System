package com.ruoyi.updatedel.repository;

import com.ruoyi.updatedel.domain.SysUser;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SysUserRepository {
    private final JdbcTemplate jdbcTemplate;
    private final BeanPropertyRowMapper<SysUser> rowMapper = BeanPropertyRowMapper.newInstance(SysUser.class);

    public SysUserRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<SysUser> findById(Long userId) {
        List<SysUser> list = jdbcTemplate.query("select user_id, user_name, password, role_level from sys_user where user_id = ?", rowMapper, userId);
        return list.stream().findFirst();
    }

    public Optional<SysUser> findByUserName(String userName) {
        List<SysUser> list = jdbcTemplate.query("select user_id, user_name, password, role_level from sys_user where user_name = ?", rowMapper, userName);
        return list.stream().findFirst();
    }

    public int updateRoleLevel(Long userId, Integer roleLevel) {
        return jdbcTemplate.update("update sys_user set role_level = ? where user_id = ?", roleLevel, userId);
    }
}
