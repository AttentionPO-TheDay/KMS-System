package com.ruoyi.keymanage.service;

import com.ruoyi.keymanage.domain.ComParam;
import com.ruoyi.keymanage.domain.UserIdentity;
import com.ruoyi.keymanage.domain.PartialKey;
import org.bouncycastle.math.ec.ECPoint;

public interface IGenerator {

    /**
     * 生成部分私钥
     *
     * @param userIdentity 用户标识
     * @param uA 用户部分公钥
     * @return 部分私钥
     */
    public PartialKey genPartialKey(UserIdentity userIdentity, String uA);

    /**
     * 获取公共参数
     *
     * @return 部分私钥
     */
    public ComParam getComParam();

    /**
     * 设置公共参数
     *
     * @param comParam 公共参数
     * @return
     */
    public int setComParam(ComParam comParam);
}
