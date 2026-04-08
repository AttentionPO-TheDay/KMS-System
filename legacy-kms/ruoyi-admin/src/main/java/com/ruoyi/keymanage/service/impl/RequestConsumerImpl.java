package com.ruoyi.keymanage.service.impl;

import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.keymanage.service.RequestConsumer;
import com.ruoyi.keymanage.service.Requestor;
import com.ruoyi.keyuser.domain.KeyUser;
import com.ruoyi.keyuser.service.IKeyUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class RequestConsumerImpl implements RequestConsumer {



    private static IKeyUserService keyUserService;

    @Autowired
    public void setKeyUserService(IKeyUserService service) {
        keyUserService = service;
    }

    @Override
    public Requestor.PasswordRequestor getPasswordRequestorByUser(String user) {
        return PasswordRequestorImpl.ofUser(user);
    }

    @Override
    public Requestor.SimplePasswordRequestor getSimplePasswordRequestorByKeyId(String keyId) {
        return SimpleasswordRequestorImpl.ofKeyId(keyId);
    }

    private static class PasswordRequestorImpl implements Requestor.PasswordRequestor {
        private final String user;

        private final String password;


        private PasswordRequestorImpl(String user, String password) {
          this.user = user;
          this.password = password;
        }

        public static PasswordRequestorImpl ofUser(String user) {
            //改成从数据库里查询有没有这个user，而非map对
            KeyUser keyUserSelect = new KeyUser();
            keyUserSelect.setUserName(user);
            keyUserSelect.setNickName(user);

            System.out.println(keyUserService.selectKeyUserList(keyUserSelect));
            if (keyUserService.selectKeyUserList(keyUserSelect) == null || keyUserService.selectKeyUserList(keyUserSelect).isEmpty()){
                return null;
            }else{
                List<KeyUser> keyUserList =keyUserService.selectKeyUserList(keyUserSelect);
                KeyUser keyUser = keyUserList.get(0);
                String password = keyUser.getPassword();
                return new PasswordRequestorImpl(user,password);
            }
        }

        @Override
        public String getName() {
          return "passwordrequestor-" + user;
        }

        @Override
        public boolean authenticate(char[] password) {
            String passwordString = new String(password);
            return authenticate(passwordString);
        }

        @Override
        public boolean authenticate(byte[] password) {
          String passwordString = password == null ? null : new String(password, StandardCharsets.UTF_8);
          return authenticate(passwordString);
        }

        @Override
        public boolean authenticate(String password) {
            return SecurityUtils.matchesPassword(password, this.password);
        }

        @Override
        public boolean isPermitted(Permission permission) {
            //System.out.println("Permisson:" + permission);
            return true;
        }
    }

    private static class SimpleasswordRequestorImpl implements Requestor.SimplePasswordRequestor {
        private final String user;
        private final char[] password;
        private final String keyId;

        protected final static Map<String, char[]> passwordMap = new HashMap<>();

        private SimpleasswordRequestorImpl(String user, char[] password, String keyId) {
            this.user = user;
            this.password = password;
            this.keyId = keyId;
        }

        public static SimpleasswordRequestorImpl ofKeyId(String keyId) {
            //此处通过keyid取出password和user
            String user = keyId;
            char[] password = passwordMap.get(user);
            if (password == null) {
                return null;
            }
            return new SimpleasswordRequestorImpl(user, password, keyId);
        }

        @Override
        public String getName() {
            return "extendedpasswordrequestor-" + user;
        }

        @Override
        public boolean isPermitted(Permission permissions) {
            return true;
        }

        @Override
        public String getKeyId() {
            return keyId;
        }

        @Override
        public char[] getPassword() {
            return password;
        }
    }
}
