package com.ruoyi.updatedel.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.math.BigInteger;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.client.protocol.response.BcosTransactionReceipt;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple7;
import com.ruoyi.updatedel.contracts.KeyEvidence;
import com.ruoyi.updatedel.mapper.KeymanageMapper;
import org.springframework.kafka.core.KafkaTemplate;

class NodeFiscoEvidenceTest {
    private static final String CONTRACT = "0x" + String.join("", Collections.nCopies(40, "1"));
    private static final String OWNER = "0x" + String.join("", Collections.nCopies(40, "2"));
    private static final String TX = "0x" + String.join("", Collections.nCopies(64, "3"));

    private Map<String, Object> request() {
        Map<String, Object> values = new HashMap<>();
        values.put("nodeId", "TEST_ONLY_NODE"); values.put("algorithm", "SM2");
        values.put("keyId", "test"); values.put("keyVersion", "1");
        values.put("publicMaterial", "04abcd"); values.put("publicKeyHash", NodeFiscoMaterial.sha256("04abcd"));
        values.put("txId", TX); values.put("signedTransaction", "aabb");
        return values;
    }

    @Test void independentKeysStartAtOneAndOversizeNeverReachesAbi() {
        Map<String, Object> values = request();
        NodeFiscoMaterial first = new NodeFiscoMaterial(values);
        assertEquals(BigInteger.ONE, first.version);
        assertTrue(first.chainKeyId.bitLength() == 256);
        values.put("keyId", "new-test");
        assertNotEquals(first.chainKeyId, new NodeFiscoMaterial(values).chainKeyId);
        values.put("keyVersion", "2");
        assertNotEquals(first.chainKeyId, new NodeFiscoMaterial(values).chainKeyId);
        values.put("publicMaterial", String.join("", Collections.nCopies(8193, "x")));
        assertThrows(IllegalArgumentException.class, () -> new NodeFiscoMaterial(values));
        values.put("publicMaterial", "sha256:" + values.get("publicKeyHash"));
        assertEquals(71, new NodeFiscoMaterial(values).material.length());
    }

    @Test void rejectsDigestMismatchAndInvalidAlgorithm() {
        Map<String, Object> values = request(); values.put("publicMaterial", "wrong");
        assertThrows(IllegalArgumentException.class, () -> new NodeFiscoMaterial(values));
        final Map<String,Object> invalid = request(); invalid.put("algorithm", "PRIVATE");
        assertThrows(IllegalArgumentException.class, () -> new NodeFiscoMaterial(invalid));
    }

    @Test void unsignedTransactionUsesActualChainAndGroupNotTheTransferValue() {
        Client client=mock(Client.class);
        org.fisco.bcos.sdk.model.NodeVersion version=mock(org.fisco.bcos.sdk.model.NodeVersion.class);
        org.fisco.bcos.sdk.model.NodeVersion.ClientVersion details=new org.fisco.bcos.sdk.model.NodeVersion.ClientVersion();
        details.setChainId("7"); when(version.getNodeVersion()).thenReturn(details);
        when(client.getClientNodeVersion()).thenReturn(version); when(client.getGroupId()).thenReturn(1);
        when(client.getBlockLimit()).thenReturn(BigInteger.valueOf(1000));
        org.fisco.bcos.sdk.transaction.model.po.RawTransaction raw=NodeFiscoMaterial.unsignedTransaction(client,CONTRACT,"0x1234");
        assertEquals(BigInteger.valueOf(7),raw.getFiscoChainId());
        assertEquals(BigInteger.ONE,raw.getGroupId());
        assertEquals(BigInteger.valueOf(1000),raw.getBlockLimit());
        verify(client,never()).sendRawTransactionAndGetReceipt(anyString());
    }

    @Test void transactionIdHashesCompleteSignedRlpNotUnsignedSigningHash() {
        org.fisco.bcos.sdk.crypto.CryptoSuite suite = new org.fisco.bcos.sdk.crypto.CryptoSuite(0);
        // Synthetic ephemeral account and offline raw transaction; never sent to any chain.
        CryptoKeyPair account = suite.createKeyPair();
        Client client = mock(Client.class);
        org.fisco.bcos.sdk.model.NodeVersion version = mock(org.fisco.bcos.sdk.model.NodeVersion.class);
        org.fisco.bcos.sdk.model.NodeVersion.ClientVersion details = new org.fisco.bcos.sdk.model.NodeVersion.ClientVersion();
        details.setChainId("1"); when(version.getNodeVersion()).thenReturn(details);
        when(client.getClientNodeVersion()).thenReturn(version); when(client.getGroupId()).thenReturn(1);
        when(client.getBlockLimit()).thenReturn(BigInteger.valueOf(1000));
        org.fisco.bcos.sdk.transaction.model.po.RawTransaction raw = NodeFiscoMaterial.unsignedTransaction(client, CONTRACT, "0x1234");
        org.fisco.bcos.sdk.transaction.codec.encode.TransactionEncoderService encoder = new org.fisco.bcos.sdk.transaction.codec.encode.TransactionEncoderService(suite);
        String signed = encoder.encodeAndSign(raw, account);
        String hash = NodeFiscoMaterial.signedTransactionHash(suite, signed);
        assertEquals("0x" + org.bouncycastle.util.encoders.Hex.toHexString(suite.hash(org.fisco.bcos.sdk.utils.Numeric.hexStringToByteArray(signed))), hash);
        assertNotEquals("0x" + org.bouncycastle.util.encoders.Hex.toHexString(encoder.encodeAndHashBytes(raw, account)), hash);
        assertEquals(hash, NodeFiscoMaterial.signedTransactionHash(suite, signed.replaceFirst("^0x", "")));
        assertThrows(IllegalArgumentException.class, () -> NodeFiscoMaterial.signedTransactionHash(suite, "abc"));
        verify(client, never()).sendRawTransactionAndGetReceipt(anyString());
    }

    private UpdatedelChainService chain(Client client, KeyEvidence evidence) throws Exception {
        UpdatedelChainService service = new UpdatedelChainService(mock(KeymanageMapper.class), mock(KafkaTemplate.class), mock(KeyOperationRecordService.class));
        Class<?> type = Class.forName(UpdatedelChainService.class.getName() + "$FiscoBcosWrapper");
        Object wrapper = mock(type, CALLS_REAL_METHODS); // No SDK constructor, network or real account.
        CryptoKeyPair account = mock(CryptoKeyPair.class); when(account.getAddress()).thenReturn(OWNER);
        ReflectionTestUtils.setField(wrapper, "client", client);
        ReflectionTestUtils.setField(wrapper, "keyEvidence", evidence);
        ReflectionTestUtils.setField(wrapper, "contractAddress", CONTRACT);
        ReflectionTestUtils.setField(wrapper, "nodeEvidenceAccount", account);
        ReflectionTestUtils.setField(service, "fiscoWrapper", wrapper);
        ReflectionTestUtils.setField(service, "fiscoPrivateKey", "TEST_ONLY_NOT_A_REAL_KEY");
        ReflectionTestUtils.setField(service, "chainWritesEnabled", true);
        return service;
    }

    private TransactionReceipt receipt(NodeFiscoMaterial material, KeyEvidence evidence) {
        TransactionReceipt receipt = mock(TransactionReceipt.class);
        when(receipt.getTransactionHash()).thenReturn(TX); when(receipt.getTo()).thenReturn(CONTRACT);
        when(receipt.getFrom()).thenReturn(OWNER); when(receipt.getBlockNumber()).thenReturn("0x10");
        when(receipt.isStatusOK()).thenReturn(true);
        when(evidence.getUploadKeyInput(receipt)).thenReturn(new Tuple7<>(material.chainKeyId, material.nodeId, material.material, material.algorithm, material.keyRef, false, material.version));
        KeyEvidence.UploadSuccessEventResponse event = new KeyEvidence.UploadSuccessEventResponse();
        event.keyId=material.chainKeyId; event.version=material.version; event.status=BigInteger.ZERO;
        when(evidence.getUploadSuccessEvents(receipt)).thenReturn(Collections.singletonList(event));
        return receipt;
    }

    @Test void confirmsOnlyMatchingTransactionInputAndUploadEvent() throws Exception {
        Map<String,Object> request = request(); NodeFiscoMaterial material = new NodeFiscoMaterial(request);
        Client client=mock(Client.class); KeyEvidence evidence=mock(KeyEvidence.class);
        TransactionReceipt receipt=receipt(material,evidence);
        BcosTransactionReceipt response=mock(BcosTransactionReceipt.class);
        when(response.getTransactionReceipt()).thenReturn(Optional.of(receipt)); when(client.getTransactionReceipt(TX)).thenReturn(response);
        UpdatedelChainService chain=chain(client,evidence);
        assertEquals("CONFIRMED",chain.nodeFiscoEvidence("receipt",material,request).get("status"));
        when(evidence.getUploadSuccessEvents(receipt)).thenReturn(Collections.emptyList());
        assertThrows(IllegalStateException.class, () -> chain.nodeFiscoEvidence("receipt",material,request));
        verify(client, never()).sendRawTransactionAndGetReceipt(anyString());
    }

    @Test void submissionUsesPersistedBytesAndRejectsWrongReceiptIdentity() throws Exception {
        Map<String,Object> request=request(); NodeFiscoMaterial material=new NodeFiscoMaterial(request);
        Client client=mock(Client.class); KeyEvidence evidence=mock(KeyEvidence.class);
        BcosTransactionReceipt missing=mock(BcosTransactionReceipt.class);
        when(missing.getTransactionReceipt()).thenReturn(Optional.empty()); when(client.getTransactionReceipt(TX)).thenReturn(missing);
        TransactionReceipt receipt=receipt(material,evidence);
        when(client.sendRawTransactionAndGetReceipt("aabb")).thenReturn(receipt);
        UpdatedelChainService chain=chain(client,evidence);
        assertEquals("CONFIRMED", chain.nodeFiscoEvidence("submit",material,request).get("status"));
        verify(client).sendRawTransactionAndGetReceipt("aabb");
        when(receipt.getTo()).thenReturn(OWNER);
        assertThrows(IllegalStateException.class, () -> chain.nodeFiscoEvidence("submit",material,request));
    }

    @Test void pausedWritesDoNotCreateSdkOrSendTransactions() throws Exception {
        Client client=mock(Client.class); UpdatedelChainService chain=chain(client,mock(KeyEvidence.class));
        ReflectionTestUtils.setField(chain,"chainWritesEnabled",false);
        assertThrows(IllegalStateException.class, () -> chain.nodeFiscoEvidence("prepare",new NodeFiscoMaterial(request()),request()));
        verifyNoInteractions(client);
    }
}
