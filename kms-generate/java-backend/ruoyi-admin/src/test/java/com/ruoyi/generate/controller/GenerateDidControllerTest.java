package com.ruoyi.generate.controller;

import com.alibaba.fastjson2.JSON;
import com.ruoyi.common.core.domain.entity.SysUser;
import com.ruoyi.common.core.domain.model.LoginUser;
import com.ruoyi.generate.domain.Keymanage;
import com.ruoyi.generate.client.GoBackendClient;
import com.ruoyi.generate.mapper.KeymanageMapper;
import org.junit.jupiter.api.*;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class GenerateDidControllerTest {
    private final String pid = new String(new char[182]).replace('\0', 'a');
    private KeymanageMapper keys;
    private GenerateDidController controller;
    private MockRestServiceServer bridge;
    @BeforeEach void setup() {
        keys = mock(KeymanageMapper.class); controller = new GenerateDidController(keys);
        ReflectionTestUtils.setField(controller,"bridgeUrl","http://bridge.invalid/internal/fabric-did");
        ReflectionTestUtils.setField(controller,"token","offline-token");
        bridge = MockRestServiceServer.createServer((RestTemplate)ReflectionTestUtils.getField(controller,"http"));
        LoginUser user = new LoginUser(); user.setUserId(7L); user.setUser(new SysUser());
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(user,null));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }
    @Test void kafkaSnakeCaseIsPreservedInPublicGenerationResponse() {
        Keymanage key = JSON.parseObject("{\"sys_pid\":\""+pid+"\",\"did_request_id\":\"original-request\"}",Keymanage.class);
        assertEquals(pid,key.getSysPid()); assertEquals("original-request",key.getDidRequestId());
        assertTrue(JSON.toJSONString(key).contains("\"sysPid\""));
    }
    @Test void anotherUsersIdentifierDoesNotReachBridge() {
        assertEquals(404, controller.query(pid).get("code"));
        verify(keys).selectBySysPid(pid,7L); bridge.verify();
    }
    @Test void queryUsesOnlyVerifyAndRequiresCompleteEvidence() {
        Keymanage key=new Keymanage(); key.setKeyId(12L); key.setDidRequestId("original-request");
        when(keys.selectBySysPid(pid,7L)).thenReturn(key);
        bridge.expect(requestTo("http://bridge.invalid/internal/fabric-did/sys-pids/verify"))
              .andExpect(header("X-Internal-Token","offline-token"))
              .andExpect(content().json("{\"sysPid\":\""+pid+"\"}"))
              .andRespond(withSuccess("{\"code\":200,\"data\":{\"provider\":\"FABRIC_DID\",\"sysPid\":\""+pid+
                 "\",\"status\":\"CONFIRMED\",\"transactionValid\":true,\"metadataMatches\":false}}",MediaType.APPLICATION_JSON));
        assertEquals(502,controller.query(pid).get("code")); bridge.verify();
    }
    @Test void completeQueryReturnsOriginalIdentifierAndTransaction() {
        Keymanage key=new Keymanage(); key.setKeyId(12L); key.setDidRequestId("original-request");
        when(keys.selectBySysPid(pid,7L)).thenReturn(key);
        bridge.expect(requestTo("http://bridge.invalid/internal/fabric-did/sys-pids/verify"))
            .andRespond(withSuccess("{\"code\":200,\"data\":{\"provider\":\"FABRIC_DID\",\"sysPid\":\""+pid+
                "\",\"txId\":\"original-tx\",\"status\":\"CONFIRMED\",\"transactionValid\":true,\"metadataMatches\":true}}",MediaType.APPLICATION_JSON));
        com.ruoyi.common.core.domain.AjaxResult reply=controller.query(pid);
        assertEquals(200,reply.get("code"));
        assertEquals("original-tx",((java.util.Map<?,?>)reply.get("data")).get("txId"));
        bridge.verify();
    }
    @Test void javaGatewayReturnsGoSysPidAlongsideOriginalGenerationMaterial() {
        GoBackendClient client=new GoBackendClient();
        ReflectionTestUtils.setField(client,"goBackendUrl","http://go.invalid");
        ReflectionTestUtils.setField(client,"internalToken","offline-token");
        MockRestServiceServer go=MockRestServiceServer.createServer((RestTemplate)ReflectionTestUtils.getField(client,"restTemplate"));
        go.expect(requestTo("http://go.invalid/generate/request/ENROLL_KEY"))
            .andExpect(header("X-Kms-User","offline-user"))
            .andRespond(withSuccess("{\"code\":200,\"data\":\"OFFLINE_GENERATION_RESULT\",\"sysPid\":\""+pid+
                "\",\"didRequestId\":\"request-1\",\"didOnchain\":{\"status\":\"PENDING_VERIFICATION\"}}",MediaType.APPLICATION_JSON));
        Keymanage key=new Keymanage();key.setUserName("offline-user");key.setEncrytName("SM2");
        assertEquals("OFFLINE_GENERATION_RESULT",client.enrollKey(key,"offline-user"));
        assertEquals(pid,key.getSysPid());assertEquals("request-1",key.getDidRequestId());
        assertEquals("PENDING_VERIFICATION",key.getDidOnchain().get("status"));go.verify();
    }
    @Test void batchMapperBindsIdentifiersForEachGeneratedKey() throws Exception {
        org.apache.ibatis.session.Configuration config=new org.apache.ibatis.session.Configuration();
        try (java.io.InputStream input=getClass().getClassLoader().getResourceAsStream("mapper/generate/KeymanageMapper.xml")) {
            new org.apache.ibatis.builder.xml.XMLMapperBuilder(input,config,"mapper/generate/KeymanageMapper.xml",config.getSqlFragments()).parse();
        }
        Keymanage first=new Keymanage(); first.setSysPid(pid);first.setDidRequestId("request-1");
        Keymanage second=new Keymanage();second.setSysPid(pid.replace('a','b'));second.setDidRequestId("request-2");
        org.apache.ibatis.mapping.BoundSql bound=config.getMappedStatement("com.ruoyi.generate.mapper.KeymanageMapper.insertKeymanageBatch")
            .getBoundSql(java.util.Collections.singletonMap("list",java.util.Arrays.asList(first,second)));
        assertTrue(bound.getSql().contains("sys_pid, did_request_id"));
        java.util.List<Object> identifiers=new java.util.ArrayList<>();
        for (org.apache.ibatis.mapping.ParameterMapping item:bound.getParameterMappings()) {
            if (item.getProperty().endsWith(".sysPid") || item.getProperty().endsWith(".didRequestId"))
                identifiers.add(bound.getAdditionalParameter(item.getProperty()));
        }
        assertEquals(java.util.Arrays.asList(pid,"request-1",pid.replace('a','b'),"request-2"),identifiers);
    }
}
