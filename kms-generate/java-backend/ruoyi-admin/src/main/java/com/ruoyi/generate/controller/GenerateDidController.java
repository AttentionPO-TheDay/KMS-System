package com.ruoyi.generate.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.ruoyi.common.core.controller.BaseController;
import com.ruoyi.common.core.domain.AjaxResult;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.mapper.KeymanageMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import java.net.Proxy;
import java.util.Collections;

/** Query the original transaction using its public SysPid; never submits from a query endpoint. */
@RestController
@RequestMapping("/generate/did")
public class GenerateDidController extends BaseController {
    private final KeymanageMapper keys;
    private final RestTemplate http;
    @Value("${FABRIC_DID_BRIDGE_URL:http://fabric-did-bridge:9094/internal/fabric-did}")
    private String bridgeUrl;
    @Value("${INTERNAL_TOKEN:}")
    private String token;

    public GenerateDidController(KeymanageMapper keys) {
        this.keys = keys;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setProxy(Proxy.NO_PROXY); factory.setConnectTimeout(3000); factory.setReadTimeout(30000);
        http = new RestTemplate(factory);
    }

    @PreAuthorize("isAuthenticated()")
    @GetMapping("/query")
    public AjaxResult query(@RequestParam String sysPid) {
        if (!sysPid.matches("[0-9a-f]{182}")) return AjaxResult.error("SysPid 格式无效");
        Keymanage key = keys.selectBySysPid(sysPid, getUserId());
        if (key == null) return AjaxResult.error(404, "未找到当前用户的生成记录；刚生成的记录请等待后台入库后重试");
        if (token.isEmpty()) return AjaxResult.error(503, "DID_QUERY_NOT_CONFIGURED");
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON); headers.set("X-Internal-Token", token);
            ResponseEntity<String> response = http.postForEntity(bridgeUrl.replaceAll("/+$", "") + "/sys-pids/verify",
                    new HttpEntity<>(JSON.toJSONString(Collections.singletonMap("sysPid", sysPid)), headers), String.class);
            JSONObject envelope = JSON.parseObject(response.getBody());
            JSONObject data = envelope.getJSONObject("data");
            if (envelope.getIntValue("code") != 200 || data == null || !sysPid.equals(data.getString("sysPid"))
                    || !"FABRIC_DID".equals(data.getString("provider"))) return AjaxResult.error(502, "DID_QUERY_RESPONSE_MISMATCH");
            if ("CONFIRMED".equals(data.getString("status")) && (!Boolean.TRUE.equals(data.getBoolean("transactionValid"))
                    || !Boolean.TRUE.equals(data.getBoolean("metadataMatches")))) return AjaxResult.error(502, "DID_CONFIRMATION_INCOMPLETE");
            data.put("keyId", key.getKeyId()); data.put("didRequestId", key.getDidRequestId());
            return AjaxResult.success("DID 上链记录查询完成", data);
        } catch (Exception e) {
            return AjaxResult.error(503, "DID_QUERY_UNAVAILABLE；请使用同一 SysPid 稍后查询");
        }
    }
}
