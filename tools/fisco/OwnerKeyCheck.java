import java.nio.file.*;
import java.security.*;
import java.security.spec.*;
import java.util.Base64;
import java.math.BigInteger;

import org.fisco.bcos.sdk.crypto.CryptoSuite;

/**
 * 从 console 的 PEM(PKCS#8, secp256k1) 私钥推导 FISCO 账户地址，
 * 并与合约 owner 比对。
 *
 * 用法: java OwnerKeyCheck <pemPath> <expectedOwner>
 */
public class OwnerKeyCheck {

    public static void main(String[] args) throws Exception {
        String pemPath = args[0];
        String expected = args.length > 1 ? args[1].toLowerCase() : "";

        String pem = new String(Files.readAllBytes(Paths.get(pemPath)), "UTF-8");
        String b64 = pem.replaceAll("-----[A-Z ]+-----", "").replaceAll("\\s", "");
        byte[] der = Base64.getDecoder().decode(b64);

        KeyFactory kf = KeyFactory.getInstance("EC");
        PrivateKey pk = kf.generatePrivate(new PKCS8EncodedKeySpec(der));

        // SunEC 的 ECPrivateKeyImpl 有 getS()，用反射取出私钥标量
        BigInteger s;
        try {
            java.lang.reflect.Method m = pk.getClass().getMethod("getS");
            s = (BigInteger) m.invoke(pk);
        } catch (NoSuchMethodException e) {
            // 兜底：从 PKCS#8 DER 中定位 0x04 0x20 <32字节>
            int idx = -1;
            for (int i = 0; i + 34 <= der.length; i++) {
                if ((der[i] & 0xFF) == 0x04 && (der[i + 1] & 0xFF) == 0x20) { idx = i + 2; break; }
            }
            if (idx < 0) throw new IllegalStateException("无法定位私钥标量");
            byte[] raw = new byte[32];
            System.arraycopy(der, idx, raw, 0, 32);
            s = new BigInteger(1, raw);
        }

        String hex = s.toString(16);
        while (hex.length() < 64) hex = "0" + hex;

        System.out.println("PRIVATE_KEY_HEX=" + hex);

        CryptoSuite cs = new CryptoSuite(1);
        String derived = cs.createKeyPair(hex).getAddress();
        System.out.println("DERIVED_ADDRESS=" + derived);
        System.out.println("EXPECTED_OWNER =" + expected);
        System.out.println("MATCH=" + derived.equalsIgnoreCase(expected));
    }
}
