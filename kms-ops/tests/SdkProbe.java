import org.fisco.bcos.sdk.BcosSDK;
import org.fisco.bcos.sdk.client.Client;

/**
 * 最小 SDK 探针：只做一件事 —— 用给定 config.toml（含 TLS 证书目录）连链，
 * 打印 blockNumber / 共识状态。
 *
 * 用法: java -cp "lib/*;." SdkProbe <config.toml 绝对路径>
 *
 * 之所以要它：KMS 的 Java 后端连链失败时只留一句 FISCO_NOT_READY，
 * 分不清是"证书不匹配"、"端口不通"还是"链没出块"。这个探针把三者分开。
 */
public class SdkProbe {
    public static void main(String[] args) {
        if (args.length < 1) {
            System.out.println("用法: SdkProbe <config.toml>");
            System.exit(2);
        }
        String cfg = args[0];
        System.out.println("[probe] config = " + cfg);
        long t0 = System.currentTimeMillis();
        try {
            BcosSDK sdk = BcosSDK.build(cfg);
            System.out.println("[probe] BcosSDK.build OK  (+" + (System.currentTimeMillis() - t0) + "ms)");
            Client client = sdk.getClient(1);
            System.out.println("[probe] client(group=1) OK");
            System.out.println("[probe] blockNumber = " + client.getBlockNumber().getBlockNumber());
            System.out.println("[probe] totalTransactionCount = "
                    + client.getTotalTransactionCount().getTotalTransactionCount().getBlockNumber());
            System.out.println("[probe] sealerList size = " + client.getSealerList().getSealerList().size());
            System.out.println("[probe] pbftView = " + client.getPbftView().getPbftView());
            System.out.println("[probe] nodeID = " + client.getNodeIDList().getNodeIDList().size());
            System.out.println("[probe] RESULT: OK");
            System.exit(0);   // SDK 的 netty 线程不会自己退
        } catch (Throwable e) {
            System.out.println("[probe] RESULT: FAIL  (" + (System.currentTimeMillis() - t0) + "ms)");
            System.out.println("[probe] " + e.getClass().getName() + ": " + e.getMessage());
            Throwable c = e.getCause();
            int depth = 0;
            while (c != null && depth++ < 5) {
                System.out.println("[probe]   caused by " + c.getClass().getName() + ": " + c.getMessage());
                c = c.getCause();
            }
        }
    }
}
