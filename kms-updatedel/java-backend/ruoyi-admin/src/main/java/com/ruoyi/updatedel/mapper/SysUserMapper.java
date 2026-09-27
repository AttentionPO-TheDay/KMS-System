package com.ruoyi.updatedel.mapper;

import com.ruoyi.updatedel.domain.SysUser;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface SysUserMapper {
    SysUser selectUserById(Long userId);

    SysUser selectUserByUserName(String userName);

    /**
     * 列出账号（供管理端的「用户选择器」用，见 P3 步骤 10）。
     *
     * <p>只返回**身份分流必需的最小字段**：`user_id` / `user_name` / `role_level`。
     * 用户列表本身是敏感信息（能枚举出系统里有哪些账号），
     * 因此调用方必须是管理员 —— 这一点由接口层的角色判定保证，不靠 SQL。
     *
     * @param keyword 可选的用户名模糊匹配（管理员主动搜索时才用）
     */
    List<SysUser> selectUserList(@Param("keyword") String keyword);

    // 原先这里有一个 updateRoleLevel(userId, roleLevel)。
    // 已删除：临时权限审批流曾借它把申请人写成「管理员」（role_level=0）或已废弃的「中级用户」（role_level=1），
    // 而 role_level 现在是登录分流的唯一判据（D9/D13），必须保持为纯静态的账号属性。
    // 保留一个能静默改写权限等级的方法本身就是隐患，故连同 Mapper XML 里的语句一并移除。
}
