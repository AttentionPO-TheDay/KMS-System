import com.ruoyi.keymanage.contracts.KeyEvidence;
import org.fisco.bcos.sdk.BcosSDK;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.crypto.CryptoSuite;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.model.CryptoType;
import org.fisco.bcos.sdk.model.TransactionReceipt;

import java.math.BigInteger;

/**
 * 部署 KeyEvidence 合约并做一次真实写入 —— 用来回答一个具体问题：
 * **这条链在有交易时到底落不落块？**
 *
 * 背景：空载运行时日志里只有 "Generating seal on,blkNum=1,tx=0" 然后立刻换视图，
 * 永远没有 commit。若这属于"空块被省略"，那么链是好的，缺的只是一笔交易；
 * 若发了交易仍然不落块，那才是共识真的坏了。二者修法完全不同，必须实测分辨。
 *
 * 用法:
 *   java -cp "lib/*;out" DeployKeyEvidence <config.toml> <hexPrivateKey>
 *
 * 合约是 onlyOwner：部署账户必须与 KMS 后端用于签名的账户**同一个**，
 * 否则后续 uploadKey/rotateKey 会 revert（现象是"上链失败"，很容易误判成链的问题）。
 */
public class DeployKeyEvidence {

    public static void main(String[] args) {
        if (args.length < 2) {
            System.out.println("用法: DeployKeyEvidence <config.toml> <hexPrivateKey>");
            System.exit(2);
        }
        String cfgPath = args[0];
        String privKey = args[1].startsWith("0x") ? args[1].substring(2) : args[1];

        try {
            System.out.println("[deploy] 连接链 ...");
            BcosSDK sdk = BcosSDK.build(cfgPath);
            Client client = sdk.getClient(1);

            CryptoSuite suite = new CryptoSuite(CryptoType.ECDSA_TYPE);
            CryptoKeyPair keyPair = suite.createKeyPair(privKey);
            System.out.println("[deploy] 部署账户 = " + keyPair.getAddress());

            long before = client.getBlockNumber().getBlockNumber().longValue();
            System.out.println("[deploy] 部署前 blockNumber = " + before);

            System.out.println("[deploy] 部署 KeyEvidence ...");
            long t0 = System.currentTimeMillis();
            KeyEvidence contract = KeyEvidence.deploy(client, keyPair);
            long cost = System.currentTimeMillis() - t0;

            String address = contract.getContractAddress();
            TransactionReceipt rc = contract.getDeployReceipt();
            System.out.println("[deploy] 合约地址 = " + address);
            System.out.println("[deploy] 回执状态 = " + (rc == null ? "null" : rc.getStatus())
                    + "  区块号 = " + (rc == null ? "null" : rc.getBlockNumber())
                    + "  gasUsed = " + (rc == null ? "null" : rc.getGasUsed())
                    + "  耗时 = " + cost + "ms");
            System.out.println("[deploy] 部署后 blockNumber = " + client.getBlockNumber().getBlockNumber().longValue());

            // ---- 真实写入：证明"有交易就落块"----
            BigInteger keyId = BigInteger.valueOf(System.currentTimeMillis() % 1000000 + 100000);
            System.out.println("[deploy] 试写 uploadKey(keyId=" + keyId + ") ...");
            TransactionReceipt up = contract.uploadKey(keyId, "probe-user", "PROBE_PUBKEY",
                    "SM2", "probe", false, BigInteger.ONE);
            System.out.println("[deploy] uploadKey 状态 = " + up.getStatus()
                    + "  区块号 = " + up.getBlockNumber()
                    + "  txHash = " + up.getTransactionHash());
            System.out.println("[deploy] 写入后 blockNumber = " + client.getBlockNumber().getBlockNumber().longValue());

            System.out.println("[deploy] 试写 changeKeyStatus ...");
            TransactionReceipt ch = contract.changeKeyStatus(keyId, BigInteger.valueOf(2));
            System.out.println("[deploy] changeKeyStatus 状态 = " + ch.getStatus()
                    + "  区块号 = " + ch.getBlockNumber());

            System.out.println("RESULT: OK");
            System.out.println("CONTRACT_ADDRESS=" + address);
        } catch (Throwable e) {
            System.out.println("RESULT: FAIL");
            System.out.println(e.getClass().getName() + ": " + e.getMessage());
            Throwable c = e.getCause();
            int d = 0;
            while (c != null && d++ < 5) {
                System.out.println("  caused by " + c.getClass().getName() + ": " + c.getMessage());
                c = c.getCause();
            }
        }
        System.exit(0);   // SDK 的 netty 线程不会自己退，不显式退出会挂住
    }
}
