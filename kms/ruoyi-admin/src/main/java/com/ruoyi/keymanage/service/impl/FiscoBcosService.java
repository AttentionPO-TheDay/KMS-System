package com.ruoyi.keymanage.service.impl;

import com.ruoyi.keymanage.contracts.KeyEvidence; // 1. 引入生成的合约类
import org.fisco.bcos.sdk.BcosSDK;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.io.File;
import java.math.BigInteger;

@Service
public class FiscoBcosService {

    // 核心对象：现在直接使用生成的 KeyEvidence 对象，而不是通用的 txProcessor
    private KeyEvidence keyEvidence;

    // 合约地址现在需要配置在 application.yml 中，或者你直接硬编码在这里
    @Value("${fisco.contract-address:0x0000000000000000000000000000000000000000}")
    private String contractAddress;

    //[group:1]> deploy KeyEvidence
    //transaction hash: 0x69deb5765e1639e679177866ca1b86eacc9993e12a2a5a28880feab715e50a4c
    //contract address: 0xadb09744949bbc4096c8b340303dfed763dae2b7
    //currentAccount: 0xd57f97659345b2b222e219666ccf5b2e19ad7e16


    @PostConstruct
    public void init() {
        try {
            System.out.println("====== [1] 初始化 FISCO BCOS SDK (Wrapper模式) ======");

            // 1. 读取外部配置文件
            File configFile = new File("config-fisco.toml");
            if (!configFile.exists()) {
                // 尝试绝对路径
                configFile = new File("/app/config-fisco.toml");
            }
            if (!configFile.exists()) {
                 throw new RuntimeException("❌ 未找到外部配置文件，请检查挂载！");
            }

            String configContent = new String(java.nio.file.Files.readAllBytes(configFile.toPath()));

            String serviceName = "fisco-node";
            try {
                System.out.println("正在解析 Docker 服务名: " + serviceName);
                java.net.InetAddress address = java.net.InetAddress.getByName(serviceName);
                String realIp = address.getHostAddress();
                System.out.println("解析成功！真实 IP 是: " + realIp);

                // C. 替换配置文件里的字符串 (把 fisco-node 换成 172.x.x.x)
                // 这样 SDK 看到的就是纯数字 IP，就不会报错了
                configContent = configContent.replace(serviceName, realIp);

            } catch (Exception e) {
                System.err.println("⚠️ DNS 解析失败，将尝试使用原配置: " + e.getMessage());
                // 如果解析失败，可能是服务名写错了，或者网络没通
            }

            // D. 把替换后的内容写入一个临时文件
            File tempConfigFile = File.createTempFile("fisco-config-resolved", ".toml");
            java.nio.file.Files.write(tempConfigFile.toPath(), configContent.getBytes());
            String finalConfigPath = tempConfigFile.getAbsolutePath();

            System.out.println("🚀 使用处理后的配置文件: " + finalConfigPath);


            // 2. 初始化 SDK (传入临时文件路径)
            BcosSDK sdk = BcosSDK.build(finalConfigPath);

            Client client = sdk.getClient(1);
            CryptoKeyPair cryptoKeyPair = client.getCryptoSuite().createKeyPair();
            System.out.println("====== [SDK] 启动成功，当前账号: " + cryptoKeyPair.getAddress() + " ======");

            if (contractAddress == null || contractAddress.equals("0x0000000000000000000000000000000000000000")) {
                System.err.println("⚠️ 警告：合约地址未配置！");
            } else {
                this.keyEvidence = KeyEvidence.load(contractAddress, client, cryptoKeyPair);
                System.out.println("✅ 合约加载成功，地址: " + contractAddress);
            }

        } catch (Exception e) {
            System.err.println("### 初始化失败 ###");
            e.printStackTrace();
            throw new RuntimeException("Init Failed", e);
        }
    }

    /**
     * 上传密钥信息
     */
    public TransactionReceipt uploadKey(Long keyId, String user, String pubKey, String algo, String usage, boolean autoUpdate, Integer version) {
        checkReady();
        try {
            // 类型转换：SDK 生成的代码通常使用 BigInteger
            BigInteger bKeyId = BigInteger.valueOf(keyId);
            BigInteger bVersion = BigInteger.valueOf(version);

            // 直接调用 Java 方法，享受强类型检查
            return keyEvidence.uploadKey(bKeyId, user, pubKey, algo, usage, autoUpdate, bVersion);
        } catch (Exception e) {
            throw new RuntimeException("区块链[uploadKey]调用失败", e);
        }
    }

    /**
     * 轮换密钥
     */
    public TransactionReceipt rotateKey(Long keyId, String newPubKey, Integer newVersion) {
        checkReady();
        try {
            BigInteger bKeyId = BigInteger.valueOf(keyId);
            BigInteger bVersion = BigInteger.valueOf(newVersion);

            return keyEvidence.rotateKey(bKeyId, newPubKey, bVersion);
        } catch (Exception e) {
            throw new RuntimeException("区块链[rotateKey]调用失败", e);
        }
    }

    /**
     * 更改密钥状态
     */
    public TransactionReceipt changeKeyStatus(Long keyId, int newStatus) {
        checkReady();
        try {
            BigInteger bKeyId = BigInteger.valueOf(keyId);
            BigInteger bStatus = BigInteger.valueOf(newStatus);

            return keyEvidence.changeKeyStatus(bKeyId, bStatus);
        } catch (Exception e) {
            throw new RuntimeException("区块链[changeKeyStatus]调用失败", e);
        }
    }

    private void checkReady() {
        if (this.keyEvidence == null) {
            throw new RuntimeException("合约未加载！请检查 application.yml 中的 fisco.contract-address 配置是否正确。");
        }
    }
}