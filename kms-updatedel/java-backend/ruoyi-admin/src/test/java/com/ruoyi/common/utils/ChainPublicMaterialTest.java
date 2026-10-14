package com.ruoyi.common.utils;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class ChainPublicMaterialTest {
    private String text(int length) {
        char[] chars = new char[length];
        Arrays.fill(chars, 'x');
        return new String(chars);
    }

    @Test void boundaryPreservesOnlyAtMost8192Utf8Bytes() {
        String limit = text(8192);
        assertEquals(limit, ChainPublicMaterial.forChain(limit));
        assertTrue(ChainPublicMaterial.forChain(text(8193)).matches("sha256:[0-9a-f]{64}"));
    }

    @Test void largeFalconPublicPackageBecomesExactDigest() throws Exception {
        String publicPackage = text(5592568);
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(publicPackage.getBytes(StandardCharsets.UTF_8));
        StringBuilder expected = new StringBuilder("sha256:");
        for (byte b : digest) expected.append(String.format("%02x", b & 255));
        String result = ChainPublicMaterial.forChain(publicPackage);
        assertEquals(expected.toString(), result);
        assertEquals(71, result.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(result, ChainPublicMaterial.forChain(result));
    }

    @Test void limitUsesBytesNotJavaCharacters() {
        String unicode = text(2731).replace('x', '\u4e2d');
        assertEquals(8193, unicode.getBytes(StandardCharsets.UTF_8).length);
        assertTrue(ChainPublicMaterial.forChain(unicode).startsWith("sha256:"));
        assertEquals("公钥", ChainPublicMaterial.forChain("公钥"));
    }

    @Test void otherUploadTextCannotExceedLimit() {
        assertEquals(text(8192), ChainPublicMaterial.requireSmall(text(8192)));
        assertThrows(IllegalArgumentException.class, () -> ChainPublicMaterial.requireSmall(text(8193)));
        assertThrows(IllegalArgumentException.class, () -> ChainPublicMaterial.forChain(null));
    }

    @Test void everySdkUploadAndRotationPathHasLastMileGuard() throws Exception {
        String source = new String(Files.readAllBytes(Paths.get(
            "src/main/java/com/ruoyi/updatedel/contracts/KeyEvidence.java")), StandardCharsets.UTF_8);
        assertTrue(source.contains("Utf8String(ChainPublicMaterial.forChain(_pubKey))"));
        assertTrue(source.contains("Utf8String(ChainPublicMaterial.forChain(_newPubKey))"));
        for (String param : new String[] { "_pubKey", "_newPubKey", "_username", "_algo", "_usage" }) {
            assertFalse(source.contains("Utf8String(" + param + ")"), "Unguarded ABI parameter " + param);
        }
    }
}
