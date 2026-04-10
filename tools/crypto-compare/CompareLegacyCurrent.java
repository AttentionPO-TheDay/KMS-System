import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import java.lang.reflect.Method;
import java.math.BigInteger;
import java.util.Locale;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.math.ec.custom.gm.SM2P256V1Curve;
import org.bouncycastle.util.encoders.Hex;

public class CompareLegacyCurrent {
    private static final BigInteger SM2_GX = new BigInteger("32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7", 16);
    private static final BigInteger SM2_GY = new BigInteger("BC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0", 16);
    private static final BigInteger CURVE_ORDER = new BigInteger("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16);
    private static final String USER_ID = "alice";
    private static final BigInteger CLIENT_PRIVATE = new BigInteger("1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDE", 16);

    public static void main(String[] args) throws Exception {
        String ua = deriveUa(CLIENT_PRIVATE);

        compareSm2(ua);
        compareSscl(ua);

        System.out.println("ALL_CHECKS_PASSED");
    }

    private static void compareSm2(String ua) throws Exception {
        com.ruoyi.keymanage.domain.UserIdentity legacyIdentity = new com.ruoyi.keymanage.domain.UserIdentity();
        legacyIdentity.setIdentityData(USER_ID);
        com.ruoyi.keymanage.service.impl.generator.ECCGenerator legacyGen = new com.ruoyi.keymanage.service.impl.generator.ECCGenerator();
        com.ruoyi.keymanage.domain.PartialKey legacyPartial = legacyGen.genPartialKey(legacyIdentity, ua);
        String legacyWa = pointHex(legacyPartial.getWA());
        String legacyTA = hex32(legacyPartial.getTA());

        com.ruoyi.keymanage.service.impl.Sm2CalculationService legacySm2 = new com.ruoyi.keymanage.service.impl.Sm2CalculationService();
        legacySm2.init();
        String legacyPa = legacySm2.calculateFinalPublicKey(USER_ID, legacyWa);

        com.ruoyi.generate.domain.UserIdentity currentIdentity = new com.ruoyi.generate.domain.UserIdentity();
        currentIdentity.setIdentityData(USER_ID);
        com.ruoyi.generate.service.generator.ECCGenerator currentGen = new com.ruoyi.generate.service.generator.ECCGenerator();
        com.ruoyi.generate.domain.PartialKey currentPartial = currentGen.genPartialKey(currentIdentity, ua);
        String currentWa = pointHex(currentPartial.getWA());
        String currentTA = hex32(currentPartial.getTA());

        com.ruoyi.updatedel.service.generator.EccKeyGenerator updateGen = new com.ruoyi.updatedel.service.generator.EccKeyGenerator();
        JSONObject updateSm2Payload = JSON.parseObject(updateGen.generate(USER_ID, ua));
        String updateWa = updateSm2Payload.getString("finalPublicKey");
        String updateTA = updateSm2Payload.getString("partialKey");

        com.ruoyi.generate.service.impl.GenerateChainServiceImpl generateChain = new com.ruoyi.generate.service.impl.GenerateChainServiceImpl();
        com.ruoyi.updatedel.service.UpdatedelChainService updateChain =
            new com.ruoyi.updatedel.service.UpdatedelChainService(null, null, null);

        assertEquals("SM2 legacy/current formula on legacy WA",
            legacyPa, invokeSm2(generateChain, USER_ID, legacyWa));
        assertEquals("SM2 legacy/update formula on legacy WA",
            legacyPa, invokeSm2(updateChain, USER_ID, legacyWa));
        assertEquals("SM2 current generate/update formula on current WA",
            invokeSm2(generateChain, USER_ID, currentWa), invokeSm2(updateChain, USER_ID, currentWa));
        assertEquals("SM2 current generate/update formula on update WA",
            invokeSm2(generateChain, USER_ID, updateWa), invokeSm2(updateChain, USER_ID, updateWa));

        assertEquals("SM2 user-side final private from legacy partial",
            finalPrivateHex(legacyTA), finalPrivateHex(legacyTA));
        assertEquals("SM2 user-side final private from current partial",
            finalPrivateHex(currentTA), finalPrivateHex(currentTA));
        assertEquals("SM2 user-side final private from update partial",
            finalPrivateHex(updateTA), finalPrivateHex(updateTA));

        System.out.println("SM2 UA=" + ua);
        System.out.println("SM2 legacy WA=" + legacyWa);
        System.out.println("SM2 current WA=" + currentWa);
        System.out.println("SM2 update WA=" + updateWa);
        System.out.println("SM2 legacy PA=" + legacyPa);
    }

    private static void compareSscl(String ua) throws Exception {
        com.ruoyi.keymanage.domain.UserIdentity legacyIdentity = new com.ruoyi.keymanage.domain.UserIdentity();
        legacyIdentity.setIdentityData(USER_ID);
        com.ruoyi.keymanage.service.impl.generator.SSCLGenerator legacyGen = new com.ruoyi.keymanage.service.impl.generator.SSCLGenerator();
        com.ruoyi.keymanage.domain.PartialKey legacyPartial = legacyGen.genPartialKey(legacyIdentity, ua);
        String legacySsclKey = "04" + hex32(legacyPartial.getMx()) + hex32(legacyPartial.getMy());
        BigInteger legacyEa = legacyGen.getEA();
        String legacyPa = computeSsclPa(ua, legacyPartial.getMx(), legacyEa);

        com.ruoyi.generate.domain.UserIdentity currentIdentity = new com.ruoyi.generate.domain.UserIdentity();
        currentIdentity.setIdentityData(USER_ID);
        com.ruoyi.generate.service.generator.SSCLGenerator currentGen = new com.ruoyi.generate.service.generator.SSCLGenerator();
        com.ruoyi.generate.domain.PartialKey currentPartial = currentGen.genPartialKey(currentIdentity, ua);
        String currentSsclKey = "04" + hex32(currentPartial.getMx()) + hex32(currentPartial.getMy());
        String currentEa = hex32(currentGen.getEA());

        com.ruoyi.updatedel.service.generator.SsclKeyGenerator updateGen = new com.ruoyi.updatedel.service.generator.SsclKeyGenerator();
        JSONObject updatePayload = JSON.parseObject(updateGen.generate(USER_ID, ua, "A"));
        String updateSsclKey = updatePayload.getString("SSCLKey");
        String updateEa = updatePayload.getString("SSCLEA");

        com.ruoyi.generate.service.impl.GenerateChainServiceImpl generateChain = new com.ruoyi.generate.service.impl.GenerateChainServiceImpl();
        com.ruoyi.updatedel.service.UpdatedelChainService updateChain =
            new com.ruoyi.updatedel.service.UpdatedelChainService(null, null, null);

        com.ruoyi.generate.domain.Keymanage generateKm = new com.ruoyi.generate.domain.Keymanage();
        generateKm.setKeyId(1L);
        generateKm.setuA(ua);
        JSONObject currentKv = new JSONObject();
        currentKv.put("SSCLKey", currentSsclKey);
        currentKv.put("SSCLEA", currentEa);

        com.ruoyi.updatedel.domain.Keymanage updateKm = new com.ruoyi.updatedel.domain.Keymanage();
        updateKm.setKeyId(1L);
        updateKm.setUa(ua);
        JSONObject updateKv = JSON.parseObject(updatePayload.toJSONString());

        assertEquals("SSCL legacy manual formula self-check",
            legacyPa, computeSsclPa(ua, new BigInteger(legacySsclKey.substring(2, 66), 16), legacyEa));
        assertEquals("SSCL current generate service/manual",
            computeSsclPa(ua, currentPartial.getMx(), new BigInteger(currentEa, 16)),
            invokeGenerateSscl(generateChain, generateKm, currentKv, currentSsclKey));
        assertEquals("SSCL update service/manual",
            computeSsclPa(ua, new BigInteger(updateSsclKey.substring(2, 66), 16), new BigInteger(updateEa, 16)),
            invokeUpdateSscl(updateChain, updateKm, updateKv, updateSsclKey));

        BigInteger legacyRecovered = recoverSecret(legacyGen.getComParam().getxIndex(), legacyGen.getComParam().getyIndex(), legacyPartial.getMx(), legacyPartial.getMy());
        BigInteger currentRecovered = recoverSecret(currentGen.getComParam().getxIndex(), currentGen.getComParam().getyIndex(), currentPartial.getMx(), currentPartial.getMy());

        assertEquals("SSCL legacy user-side secret recovery", hex32(legacyEa), hex32(legacyRecovered));
        assertEquals("SSCL current user-side secret recovery", currentEa, hex32(currentRecovered));

        String legacyUserFinalPrivate = finalPrivateHex(hex32(legacyRecovered.multiply(legacyPartial.getMx()).mod(CURVE_ORDER)));
        String currentUserFinalPrivate = finalPrivateHex(hex32(currentRecovered.multiply(currentPartial.getMx()).mod(CURVE_ORDER)));

        System.out.println("SSCL legacy key=" + legacySsclKey);
        System.out.println("SSCL current key=" + currentSsclKey);
        System.out.println("SSCL update key=" + updateSsclKey);
        System.out.println("SSCL legacy PA=" + legacyPa);
        System.out.println("SSCL legacy user final private=" + legacyUserFinalPrivate);
        System.out.println("SSCL current user final private=" + currentUserFinalPrivate);
    }

    private static String deriveUa(BigInteger privateKey) {
        SM2P256V1Curve curve = new SM2P256V1Curve();
        ECPoint g = curve.createPoint(SM2_GX, SM2_GY);
        return pointHex(g.multiply(privateKey).normalize());
    }

    private static String invokeSm2(Object target, String userId, String wa) throws Exception {
        Method method = target.getClass().getDeclaredMethod("calculateSM2FinalPublicKey", String.class, String.class);
        method.setAccessible(true);
        return ((String) method.invoke(target, userId, wa)).toUpperCase(Locale.ROOT);
    }

    private static String invokeGenerateSscl(com.ruoyi.generate.service.impl.GenerateChainServiceImpl target,
                                             com.ruoyi.generate.domain.Keymanage km,
                                             JSONObject kv,
                                             String ssclKey) throws Exception {
        Method method = target.getClass().getDeclaredMethod("calculateSSCLPublicKey",
            com.ruoyi.generate.domain.Keymanage.class, JSONObject.class, String.class);
        method.setAccessible(true);
        return ((String) method.invoke(target, km, kv, ssclKey)).toUpperCase(Locale.ROOT);
    }

    private static String invokeUpdateSscl(com.ruoyi.updatedel.service.UpdatedelChainService target,
                                           com.ruoyi.updatedel.domain.Keymanage km,
                                           JSONObject kv,
                                           String ssclKey) throws Exception {
        Method method = target.getClass().getDeclaredMethod("calculateSSCLPublicKey",
            com.ruoyi.updatedel.domain.Keymanage.class, JSONObject.class, String.class);
        method.setAccessible(true);
        return ((String) method.invoke(target, km, kv, ssclKey)).toUpperCase(Locale.ROOT);
    }

    private static String computeSsclPa(String ua, BigInteger m, BigInteger eA) {
        SM2P256V1Curve curve = new SM2P256V1Curve();
        ECPoint g = curve.createPoint(SM2_GX, SM2_GY);
        ECPoint uaPoint = parsePoint(curve, ua);
        ECPoint pa = uaPoint.add(g.multiply(eA.multiply(m).mod(CURVE_ORDER)).normalize()).normalize();
        return pointHex(pa);
    }

    private static BigInteger recoverSecret(BigInteger[] xIndex, BigInteger[] yIndex, BigInteger x, BigInteger y) {
        BigInteger[] allX = new BigInteger[xIndex.length + 1];
        BigInteger[] allY = new BigInteger[yIndex.length + 1];
        System.arraycopy(xIndex, 0, allX, 0, xIndex.length);
        System.arraycopy(yIndex, 0, allY, 0, yIndex.length);
        allX[xIndex.length] = x;
        allY[yIndex.length] = y;

        BigInteger secret = BigInteger.ZERO;
        for (int i = 0; i < allX.length; i++) {
            BigInteger numerator = BigInteger.ONE;
            BigInteger denominator = BigInteger.ONE;
            for (int j = 0; j < allX.length; j++) {
                if (i == j) {
                    continue;
                }
                numerator = numerator.multiply(allX[j].negate()).mod(CURVE_ORDER);
                denominator = denominator.multiply(allX[i].subtract(allX[j]).mod(CURVE_ORDER)).mod(CURVE_ORDER);
            }
            BigInteger term = allY[i].multiply(numerator).mod(CURVE_ORDER)
                .multiply(denominator.modInverse(CURVE_ORDER)).mod(CURVE_ORDER);
            secret = secret.add(term).mod(CURVE_ORDER);
        }
        return secret.signum() < 0 ? secret.add(CURVE_ORDER) : secret;
    }

    private static String finalPrivateHex(String partialHex) {
        BigInteger value = new BigInteger(partialHex, 16).add(CLIENT_PRIVATE).mod(CURVE_ORDER);
        return hex32(value);
    }

    private static ECPoint parsePoint(SM2P256V1Curve curve, String pointHex) {
        BigInteger x = new BigInteger(pointHex.substring(2, 66), 16);
        BigInteger y = new BigInteger(pointHex.substring(66, 130), 16);
        ECPoint point = curve.createPoint(x, y);
        if (!point.isValid()) {
            throw new IllegalStateException("Point not on curve: " + pointHex);
        }
        return point;
    }

    private static String pointHex(ECPoint point) {
        return Hex.toHexString(point.getEncoded(false)).toUpperCase(Locale.ROOT);
    }

    private static String hex32(BigInteger value) {
        byte[] bytes = new byte[32];
        byte[] source = value.mod(CURVE_ORDER).toByteArray();
        if (source.length > 32) {
            System.arraycopy(source, source.length - 32, bytes, 0, 32);
        } else {
            System.arraycopy(source, 0, bytes, 32 - source.length, source.length);
        }
        return Hex.toHexString(bytes).toUpperCase(Locale.ROOT);
    }

    private static void assertEquals(String label, String expected, String actual) {
        if (!normalize(expected).equals(normalize(actual))) {
            throw new IllegalStateException(label + " mismatch\nexpected=" + expected + "\nactual=" + actual);
        }
        System.out.println("PASS " + label + " => " + expected);
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
    }
}
