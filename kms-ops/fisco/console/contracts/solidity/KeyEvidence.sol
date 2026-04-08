pragma solidity ^0.4.24;

contract KeyEvidence {

    // ✅ 改动1：事件定义增加 version，方便链下审计历史
    event UploadSuccess(uint256 indexed keyId, uint32 version, uint8 status, uint256 timestamp);
    event StatusChanged(uint256 indexed keyId, uint32 version, uint8 newStatus, uint256 timestamp);
    event KeyRotated(uint256 indexed keyId, uint32 newVersion, uint8 status, uint256 timestamp);

    struct KeyRecord {
        uint256 keyId;
        string username;
        string publicKey;
        string algorithm;
        string usage;
        bool isAutoUpdate;
        uint8 status;      // 0=Active, 1=Frozen, 2=Rotated, 3=Revoked
        uint256 createTime;
        uint256 updateTime;
        uint32 version;    // ✅ 改动2：新增版本号字段
    }

    mapping(uint256 => KeyRecord) private records;

    // ✅ 改动3：上链方法增加 _version 参数
    function uploadKey(
        uint256 _keyId, 
        string _username, 
        string _pubKey, 
        string _algo, 
        string _usage,
        bool _isAutoUpdate,
        uint32 _version      // <--- 传入版本号 (通常为1)
    ) public returns(int256) {
        // 如果ID已存在，返回错误 (防止误覆盖)
        if (records[_keyId].keyId != 0) return -1;

        records[_keyId] = KeyRecord({
            keyId: _keyId,
            username: _username,
            publicKey: _pubKey,
            algorithm: _algo,
            usage: _usage,
            isAutoUpdate: _isAutoUpdate,
            status: 0,       // 默认 Active
            createTime: now,
            updateTime: now,
            version: _version // <--- 赋值
        });

        // 触发事件
        emit UploadSuccess(_keyId, _version, 0, now);
        return 0;
    }

    // ✅ 改动4：新增轮换/更新方法
    function rotateKey(uint256 _keyId, string _newPubKey, uint32 _newVersion) public returns(int256) {
        KeyRecord storage k = records[_keyId];
        
        // 检查是否存在
        if (k.keyId == 0) return -1;
        // 检查是否已回收 (已回收的不能更新)
        if (k.status == 3) return -2; 

        // 1. 发出“旧版本退休”事件
        // 虽然 Storage 里马上要被覆盖，但这一条日志永远留在了区块链上
        // 证明：在此时刻，旧版本 (k.version) 变成了 Rotated (2)
        emit StatusChanged(_keyId, k.version, 2, now);

        // 2. 更新 Storage 为新版本
        k.publicKey = _newPubKey;
        k.version = _newVersion;
        k.status = 0; // 新版本状态重置为 Active
        k.updateTime = now;
        
        // 3. 发出“新版本上岗”事件
        emit KeyRotated(_keyId, _newVersion, 0, now);
        return 0;
    }

    // ✅ 改动5：状态变更方法，事件带上当前 version
    function changeKeyStatus(uint256 _keyId, uint8 _newStatus) public returns(int256) {
        if (records[_keyId].keyId == 0) return -1; 
        
        records[_keyId].status = _newStatus;
        records[_keyId].updateTime = now;
        
        // 记录是哪个版本发生了状态变更
        emit StatusChanged(_keyId, records[_keyId].version, _newStatus, now);
        return 0;
    }
}