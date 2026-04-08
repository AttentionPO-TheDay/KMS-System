package com.ruoyi.generate.service;

import com.ruoyi.generate.domain.Keymanage;

/**
 * 区块链上链服务接口
 */
public interface GenerateChainService {

    /**
     * 处理密钥上链
     * @param keymanage 密钥对象
     * @return 是否成功
     */
    boolean processChainSync(Keymanage keymanage);

    /**
     * 根据密钥ID查询上链状态
     * @param keyId 密钥ID
     * @return 上链状态信息
     */
    ChainSyncStatus getChainStatus(Long keyId);

    /**
     * 链上状态结果
     */
    class ChainSyncStatus {
        private Long keyId;
        private String chainStatus;
        private String chainHash;
        private Long blockHeight;
        private String status;

        public ChainSyncStatus() {}

        public ChainSyncStatus(Long keyId, String chainStatus, String chainHash, Long blockHeight) {
            this.keyId = keyId;
            this.chainStatus = chainStatus;
            this.chainHash = chainHash;
            this.blockHeight = blockHeight;
        }

        public Long getKeyId() { return keyId; }
        public void setKeyId(Long keyId) { this.keyId = keyId; }

        public String getChainStatus() { return chainStatus; }
        public void setChainStatus(String chainStatus) { this.chainStatus = chainStatus; }

        public String getChainHash() { return chainHash; }
        public void setChainHash(String chainHash) { this.chainHash = chainHash; }

        public Long getBlockHeight() { return blockHeight; }
        public void setBlockHeight(Long blockHeight) { this.blockHeight = blockHeight; }

        public String getStatus() { return status; }
        public void setStatus(String status) { this.status = status; }
    }
}
