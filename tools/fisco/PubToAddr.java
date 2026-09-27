import java.nio.file.*;
import java.security.*;
import java.security.spec.*;
import java.util.Base64;
import java.math.BigInteger;

import org.fisco.bcos.sdk.crypto.CryptoSuite;
import org.fisco.bcos.sdk.crypto.hash.Hash;
import org.fisco.bcos.sdk.crypto.hash.Keccak256;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;

/**
 * 从 secp256k1 公钥(PEM, SubjectPublicKeyInfo)计算 FISCO 账户地址，
 * 并核对与给定地址是否一致。用于判断「密钥文件与地址是否配套」。
 *
 * 用法: java PubToAddr <pubPemPath> <expectedAddress>
 */
public class PubToAddr {

    public static void main(String[] args) throws Exception {
        String pemPath = args[0];
        String expected = args.length > 1 ? args[1].toLowerCase() : "";

        String pem = new String(Files.readAllBytes(Paths.get(pemPath)), "UTF-8");
        String b64 = pem.replaceAll("-----[A-Z ]+-----", "").replaceAll("\\s", "");
        byte[] der = Base64.getDecoder().decode(b64);

        // SubjectPublicKeyInfo 中公钥位串的最后 65 字节即 04||X||Y
        byte[] raw = null;
        for (int i = 0; i + 65 <= der.length; i++) {
            if ((der[i] & 0xFF) == 0x04) { raw = new byte[65]; System.arraycopy(der, i, raw, 0, 65); break; }
        }
        if (raw == null) throw new IllegalStateException("未能从 DER 中定位未压缩公钥");

        // FISCO 地址 = keccak256(pubKey[1..64]) 的最后 20 字节
        byte[] body = new byte[64];
        System.arraycopy(raw, 1, body, 0, 64);

        Hash hash = new Keccak256();
        byte[] h = hash.hash(body);
        StringBuilder sb = new StringBuilder("0x");
        for (int i = h.length - 20; i < h.length; i++) sb.append(String.format("%02x", h[i]));
        String addr = sb.toString();

        System.out.println("PUB_COMPUTED_ADDRESS=" + addr);
        System.out.println("EXPECTED_ADDRESS    =" + expected);
        System.out.println("MATCH=" + addr.equalsIgnoreCase(expected));
    }
}
