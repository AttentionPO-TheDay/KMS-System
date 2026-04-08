package com.ruoyi.keymanage.service;

import org.springframework.stereotype.Component;

@Component
public interface Requestor {
    enum Permission {
    ENROLL_KEY, //注册新密钥
    REENROLL_KEY, //重新注册密钥
    //GEN_KEYPAIR, //生成密钥对
    UPDATE_KEY, //密钥更新
    UNSUSPEND_KEY, //密钥恢复
    REVOKE_KEY //密钥吊销
    }

    /**
     * 返回requestor的name。
     * @return the name of this requestor
     */
    String getName();

    /**
     * 判断许可请求是否合法
     * @param permission 许可
     * @return 结果
     */
    boolean isPermitted(Permission permission);

    /**
     * 来自用户请求处理的requestor
     * 使用用户名和密码
     */
    interface PasswordRequestor extends Requestor {

        boolean authenticate(char[] password);

        boolean authenticate(byte[] password);

        boolean authenticate(String password);
    }

    /**
     * 处理特定key请求的requestor
     * 使用key_id和密码
     */
    interface SimplePasswordRequestor extends Requestor {

        String getKeyId();

        char[] getPassword();

    }
}
