package com.ruoyi.common.utils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** Last-mile ABI guard: never submit public material larger than 8 KiB. */
public final class ChainPublicMaterial {
    public static final int MAX_BYTES = 8 * 1024;

    private ChainPublicMaterial() { }

    public static String forChain(String material) {
        if (material == null) {
            throw new IllegalArgumentException("Chain public material is required");
        }
        byte[] bytes = material.getBytes(StandardCharsets.UTF_8);
        if (bytes.length <= MAX_BYTES) {
            return material;
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder hex = new StringBuilder("sha256:");
            for (byte value : digest) {
                hex.append(Character.forDigit((value >>> 4) & 15, 16));
                hex.append(Character.forDigit(value & 15, 16));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    public static String requireSmall(String value) {
        if (value == null || value.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) {
            throw new IllegalArgumentException("Chain text parameter exceeds 8 KiB or is missing");
        }
        return value;
    }
}
