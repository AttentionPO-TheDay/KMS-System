import org.fisco.bcos.sdk.crypto.CryptoSuite;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;

/**
 * 由私钥推导 FISCO 账户地址（**ECDSA / secp256k1**）。
 *
 * 重要：本链使用 ECDSA（config-fisco.toml / 节点为 secp256k1），
 *   CryptoSuite(0) = ECDSA, CryptoSuite(1) = SM2。
 *   用错 suite 会得到完全不同的地址，从而误判"应用没使用配置私钥"。
 *
 * 用法: java DeriveAddrEcdsa <hex私钥>
 */
public class DeriveAddrEcdsa {

    public static void main(String[] args) throws Exception {
        String raw = args[0].trim();
        if (raw.startsWith("0x") || raw.startsWith("0X")) raw = raw.substring(2);
        // SDK 期望定长 64 位 hex：若私钥以 0 开头，必须左补零，否则高位丢失
        while (raw.length() < 64) raw = "0" + raw;
        if (raw.length() != 64) throw new IllegalArgumentException("私钥长度非法: " + raw.length());

        CryptoSuite cs = new CryptoSuite(0); // 0 = ECDSA(secp256k1)
        CryptoKeyPair kp = cs.createKeyPair(raw);

        System.out.println("ADDRESS=" + kp.getAddress());
    }
}
