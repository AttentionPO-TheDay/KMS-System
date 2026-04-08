package com.ruoyi.keymanage.service;


public interface RequestConsumer {

    Requestor.PasswordRequestor getPasswordRequestorByUser(String user);

    Requestor.SimplePasswordRequestor getSimplePasswordRequestorByKeyId(String keyId);
}
