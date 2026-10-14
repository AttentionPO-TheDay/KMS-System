package com.ruoyi.updatedel.controller;

import com.ruoyi.updatedel.service.NodeFiscoMaterial;
import com.ruoyi.updatedel.service.UpdatedelChainService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

/** Internal network only; nginx deliberately does not publish /internal/**. */
@RestController
@RequestMapping("/internal/node-fisco")
public class InternalNodeFiscoController {
    private final UpdatedelChainService chain;
    @Value("${kms.go-backend.internal-token}") private String internalToken;
    public InternalNodeFiscoController(UpdatedelChainService chain) { this.chain = chain; }

    @PostMapping("/{operation}")
    public Map<String, Object> execute(@PathVariable String operation,
            @RequestHeader(value="X-Internal-Token", required=false) String token,
            @RequestBody Map<String, Object> request) throws Exception {
        if (internalToken == null || internalToken.isEmpty() || token == null || !MessageDigest.isEqual(internalToken.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "INVALID_INTERNAL_TOKEN");
        }
        return chain.nodeFiscoEvidence(operation, new NodeFiscoMaterial(request), request);
    }
}
