package com.ruoyi.updatedel.domain;

import lombok.Data;

@Data
public class SysUser {
    private Long userId;
    private String userName;
    private String password;
    private Integer roleLevel;
}
