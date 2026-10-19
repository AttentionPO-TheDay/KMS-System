package com.kms.fabricdid;

import com.google.protobuf.ByteString;
import org.hyperledger.fabric.protos.msp.Identities.SerializedIdentity;
import org.hyperledger.fabric.sdk.security.CryptoSuite;
import org.junit.Test;
import java.lang.reflect.Proxy;
import java.security.MessageDigest;
import org.bouncycastle.util.encoders.Hex;
import static org.junit.Assert.*;

public class CreatorIdentityTest {
    private final ByteString nonce = ByteString.copyFromUtf8("OFFLINE_NONCE");
    private final String lf = "-----BEGIN CERTIFICATE-----\nOFFLINE_CERTIFICATE\n-----END CERTIFICATE-----\n";
    // Only deterministic hashing is needed here; no SDK initialization or network calls.
    private final CryptoSuite crypto = (CryptoSuite) Proxy.newProxyInstance(CryptoSuite.class.getClassLoader(), new Class<?>[] {CryptoSuite.class},
            (proxy, method, args) -> {
                if ("hash".equals(method.getName())) return MessageDigest.getInstance("SHA-256").digest((byte[]) args[0]);
                throw new UnsupportedOperationException(method.getName());
            });
    private SerializedIdentity identity(String msp, String pem) {
        return SerializedIdentity.newBuilder().setMspid(msp).setIdBytes(ByteString.copyFromUtf8(pem)).build();
    }
    private String tx(ByteString value, SerializedIdentity creator) {
        return Hex.toHexString(crypto.hash(value.concat(creator.toByteString()).toByteArray()));
    }
    @Test public void windowsRecordCanBeVerifiedWithLinuxPem() {
        assertTrue(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf.replace("\n", "\r\n"))), nonce, identity("baas1", lf), crypto));
    }
    @Test public void linuxRecordCanBeVerifiedWithWindowsPem() {
        assertTrue(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf)), nonce, identity("baas1", lf.replace("\n", "\r\n")), crypto));
    }
    @Test public void unchangedSerializationStillMatches() {
        assertTrue(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf)), nonce, identity("baas1", lf), crypto));
    }
    @Test public void differentMspCannotMatch() {
        assertFalse(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf)), nonce, identity("other", lf), crypto));
    }
    @Test public void differentCertificateCannotMatch() {
        assertFalse(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf)), nonce, identity("baas1", lf.replace("OFFLINE_CERTIFICATE", "OTHER_CERTIFICATE")), crypto));
    }
    @Test public void differentNonceCannotMatch() {
        assertFalse(VendorDidSdk.matchesCreatorTransaction(tx(nonce, identity("baas1", lf)), ByteString.copyFromUtf8("OTHER_NONCE"), identity("baas1", lf), crypto));
    }
}
