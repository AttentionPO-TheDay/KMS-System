package com.ruoyi.generate.controller;

import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.generate.domain.ComParam;
import com.ruoyi.generate.domain.PartialKey;
import com.ruoyi.generate.domain.UserIdentity;
import com.ruoyi.generate.service.generator.SSCLGenerator;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

/** Stateless, deterministic share issuance for the external managed SSCL flow. */
@RestController
@RequestMapping("/internal/generate/sscl")
public class InternalSsclController {
    private final SSCLGenerator generator;
    @Value("${kms.go-backend.internal-token}") private String internalToken;

    public InternalSsclController(SSCLGenerator generator) { this.generator = generator; }

    @PostMapping("/partial")
    public AjaxResult partial(@RequestHeader(value="X-Internal-Token", required=false) String token,
                              @RequestBody Map<String, Object> body) {
        if (internalToken == null || internalToken.isEmpty() || token == null ||
            !MessageDigest.isEqual(internalToken.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
            return AjaxResult.error(403, "INTERNAL_AUTH_REQUIRED");
        }
        if (body == null || body.size() != 2 || !(body.get("identity") instanceof String) || !(body.get("ua") instanceof String)) {
            return AjaxResult.error(400, "INVALID_SSCL_REQUEST");
        }
        String identity = (String) body.get("identity"), ua = (String) body.get("ua");
        if (!identity.matches("ext-[0-9a-f]{60}") || !ua.matches("04[0-9a-f]{128}")) {
            return AjaxResult.error(400, "INVALID_SSCL_REQUEST");
        }
        try {
            UserIdentity user = new UserIdentity();
            user.setIdentityData(identity);
            PartialKey share = generator.genPartialKey(user, ua);
            ComParam params = generator.getComParam();
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("identity", identity);
            data.put("ua", ua);
            data.put("SSCLKey", "04" + hex(share.getMx()) + hex(share.getMy()));
            // Encode points explicitly as hex (Jackson otherwise encodes byte[] as base64).
            data.put("PPub", org.bouncycastle.util.encoders.Hex.toHexString(params.getPPub().getEncoded(false)));
            data.put("xIndex", hexes(params.getxIndex()));
            data.put("yIndex", hexes(params.getyIndex()));
            return AjaxResult.success(data);
        } catch (IllegalArgumentException ex) {
            return AjaxResult.error(400, "INVALID_SSCL_MATERIAL");
        }
    }

    private static String hex(BigInteger value) { return String.format("%064x", value); }
    private static List<String> hexes(BigInteger[] values) {
        List<String> result = new ArrayList<>();
        for (BigInteger value : values) result.add(hex(value));
        return result;
    }
}
