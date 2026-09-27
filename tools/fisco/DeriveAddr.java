import java.math.BigInteger;

import org.fisco.bcos.sdk.crypto.CryptoSuite;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;

/**
 * 由 32 字节私钥推导 FISCO 账户地址。
 *
 * 关键点（此前踩过的坑）：
 *   不能把私钥当 BigInteger 再 toString(16) 后交给 SDK —— 若私钥以 0 开头，
 *   高位 0 会丢失，导致推导出的地址与 SDK/应用实际使用的地址不一致。
 *   SDK 的 createKeyPair(String) 期望**定长 64 位 hex**，
 *   因此这里必须左补零到 64 位再传入。
 *
 * 用法: java DeriveAddr <64位hex私钥>
 */
public class DeriveAddr {

    public static void main(String[] args) throws Exception {
        String raw = args[0].trim();
        if (raw.startsWith("0x") || raw.startsWith("0X")) raw = raw.substring(2);

        // 左补零到 64 位（32 字节）
        while (raw.length() < 64) raw = "0" + raw;
        if (raw.length() != 64) {
            throw new IllegalArgumentException("私钥长度非法: " + raw.length());
        }

        CryptoSuite cs = new CryptoSuite(1);
        CryptoKeyPair kp = cs.createKeyPair(raw);

        System.out.println("PRIVATE_KEY_HEX=" + raw);
        System.out.println("ADDRESS=" + kp.getAddress());
        System.out.println("PUBLIC_KEY=" + kp.getHexPublicKey());
    }
}
