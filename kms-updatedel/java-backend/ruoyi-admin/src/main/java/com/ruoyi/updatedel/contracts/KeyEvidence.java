package com.ruoyi.updatedel.contracts;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.fisco.bcos.sdk.abi.FunctionReturnDecoder;
import org.fisco.bcos.sdk.abi.TypeReference;
import org.fisco.bcos.sdk.abi.datatypes.Bool;
import org.fisco.bcos.sdk.abi.datatypes.Event;
import org.fisco.bcos.sdk.abi.datatypes.Function;
import org.fisco.bcos.sdk.abi.datatypes.Type;
import org.fisco.bcos.sdk.abi.datatypes.Utf8String;
import org.fisco.bcos.sdk.abi.datatypes.generated.Int256;
import org.fisco.bcos.sdk.abi.datatypes.generated.Uint256;
import org.fisco.bcos.sdk.abi.datatypes.generated.Uint32;
import org.fisco.bcos.sdk.abi.datatypes.generated.Uint8;
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple1;
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple2;
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple3;
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple7;
import org.fisco.bcos.sdk.client.Client;
import org.fisco.bcos.sdk.contract.Contract;
import org.fisco.bcos.sdk.crypto.CryptoSuite;
import org.fisco.bcos.sdk.crypto.keypair.CryptoKeyPair;
import org.fisco.bcos.sdk.eventsub.EventCallback;
import org.fisco.bcos.sdk.model.CryptoType;
import org.fisco.bcos.sdk.model.TransactionReceipt;
import org.fisco.bcos.sdk.model.callback.TransactionCallback;
import org.fisco.bcos.sdk.transaction.model.exception.ContractException;

@SuppressWarnings("unchecked")
public class KeyEvidence extends Contract {
    public static final String[] BINARY_ARRAY = {"608060405234801561001057600080fd5b506108f9806100206000396000f300608060405260043610610057576000357c0100000000000000000000000000000000000000000000000000000000900463ffffffff1680631c80786d1461005c5780634b3765e2146100aa578063de07c3341461021f575b600080fd5b34801561006857600080fd5b5061009460048036038101908080359060200190929190803560ff1690602001909291905050506102b6565b6040518082815260200191505060405180910390f35b3480156100b657600080fd5b5061020960048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803515159060200190929190803563ffffffff1690602001909291905050506103cf565b6040518082815260200191505060405180910390f35b34801561022b57600080fd5b506102a060048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803563ffffffff1690602001909291905050506105e3565b6040518082815260200191505060405180910390f35b6000806000808581526020019081526020016000206000015414156102fd577fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff90506103c9565b8160008085815260200190815260200160002060050160016101000a81548160ff02191690831515021790555060408051808201909152600181526020017f75706c6f6164207375636365737300000000000000000000000000000000000081525060008086600001905550600185600101905550600184600201905550426003019055507f50b6fc6e4f31d2bf0f05397b37f5c8d789302d717c0014ee83376c2d7fd9fe208360405180808273ffffffffffffffffffffffffffffffffffffffff16815260200191505060405180910390a25060019150506103c9565b91905056"};

    public static final String BINARY = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", BINARY_ARRAY);

    public static final String[] SM_BINARY_ARRAY = {"608060405234801561001057600080fd5b506108f9806100206000396000f300608060405260043610610057576000357c0100000000000000000000000000000000000000000000000000000000900463ffffffff168063b57873791461005c578063f84daa7a146101d1578063f9b7c3b91461021f575b600080fd5b34801561006857600080fd5b506101bb60048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803515159060200190929190803563ffffffff1690602001909291905050506102b6565b6040518082815260200191505060405180910390f35b3480156101dd57600080fd5b5061020960048036038101908080359060200190929190803560ff1690602001909291905050506104ca565b6040518082815260200191505060405180910390f35b34801561022b57600080fd5b506102a060048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803563ffffffff1690602001909291905050506105e3565b6040518082815260200191505060405180910390f35b6000806000808a8152602001908152602001600020600001541415156102fe577fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff90506104bf565b610140604051908101604052808981526020018881526020018781526020018681526..."};

    public static final String SM_BINARY = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", SM_BINARY_ARRAY);

    public static final String[] ABI_ARRAY = {"[{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_newStatus\",\"type\":\"uint8\"}],\"name\":\"changeKeyStatus\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_username\",\"type\":\"string\"},{\"name\":\"_pubKey\",\"type\":\"string\"},{\"name\":\"_algo\",\"type\":\"string\"},{\"name\":\"_usage\",\"type\":\"string\"},{\"name\":\"_isAutoUpdate\",\"type\":\"bool\"},{\"name\":\"_version\",\"type\":\"uint32\"}],\"name\":\"uploadKey\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_newPubKey\",\"type\":\"string\"},{\"name\":\"_newVersion\",\"type\":\"uint32\"}],\"name\":\"rotateKey\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"version\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"status\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"UploadSuccess\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"version\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"newStatus\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"StatusChanged\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"newVersion\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"status\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"KeyRotated\",\"type\":\"event\"}]"};

    public static final String ABI = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", ABI_ARRAY);

    public static final String FUNC_CHANGEKEYSTATUS = "changeKeyStatus";
    public static final String FUNC_UPLOADKEY = "uploadKey";
    public static final String FUNC_ROTATEKEY = "rotateKey";

    public static final Event UPLOADSUCCESS_EVENT = new Event("UploadSuccess",
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));
    public static final Event STATUSCHANGED_EVENT = new Event("StatusChanged",
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));
    public static final Event KEYROTATED_EVENT = new Event("KeyRotated",
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));

    protected KeyEvidence(String contractAddress, Client client, CryptoKeyPair credential) {
        super(getBinary(client.getCryptoSuite()), contractAddress, client, credential);
    }

    public static String getBinary(CryptoSuite cryptoSuite) {
        return (cryptoSuite.getCryptoTypeConfig() == CryptoType.ECDSA_TYPE ? BINARY : SM_BINARY);
    }

    public TransactionReceipt changeKeyStatus(BigInteger keyId, BigInteger newStatus) {
        final Function function = new Function(
                FUNC_CHANGEKEYSTATUS,
                Arrays.<Type>asList(new Uint256(keyId), new Uint8(newStatus)),
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public TransactionReceipt uploadKey(BigInteger keyId, String username, String pubKey, String algo, String usage, Boolean isAutoUpdate, BigInteger version) {
        final Function function = new Function(
                FUNC_UPLOADKEY,
                Arrays.<Type>asList(new Uint256(keyId), new Utf8String(username), new Utf8String(pubKey), new Utf8String(algo), new Utf8String(usage), new Bool(isAutoUpdate), new Uint32(version)),
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public TransactionReceipt rotateKey(BigInteger keyId, String newPubKey, BigInteger newVersion) {
        final Function function = new Function(
                FUNC_ROTATEKEY,
                Arrays.<Type>asList(new Uint256(keyId), new Utf8String(newPubKey), new Uint32(newVersion)),
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public List<UploadSuccessEventResponse> getUploadSuccessEvents(TransactionReceipt transactionReceipt) {
        List<EventValuesWithLog> valueList = extractEventParametersWithLog(UPLOADSUCCESS_EVENT, transactionReceipt);
        ArrayList<UploadSuccessEventResponse> responses = new ArrayList<UploadSuccessEventResponse>(valueList.size());
        for (EventValuesWithLog eventValues : valueList) {
            UploadSuccessEventResponse typedResponse = new UploadSuccessEventResponse();
            typedResponse.log = eventValues.getLog();
            typedResponse.keyId = (BigInteger) eventValues.getIndexedValues().get(0).getValue();
            typedResponse.version = (BigInteger) eventValues.getNonIndexedValues().get(0).getValue();
            typedResponse.status = (BigInteger) eventValues.getNonIndexedValues().get(1).getValue();
            typedResponse.timestamp = (BigInteger) eventValues.getNonIndexedValues().get(2).getValue();
            responses.add(typedResponse);
        }
        return responses;
    }

    public List<StatusChangedEventResponse> getStatusChangedEvents(TransactionReceipt transactionReceipt) {
        List<EventValuesWithLog> valueList = extractEventParametersWithLog(STATUSCHANGED_EVENT, transactionReceipt);
        ArrayList<StatusChangedEventResponse> responses = new ArrayList<StatusChangedEventResponse>(valueList.size());
        for (EventValuesWithLog eventValues : valueList) {
            StatusChangedEventResponse typedResponse = new StatusChangedEventResponse();
            typedResponse.log = eventValues.getLog();
            typedResponse.keyId = (BigInteger) eventValues.getIndexedValues().get(0).getValue();
            typedResponse.version = (BigInteger) eventValues.getNonIndexedValues().get(0).getValue();
            typedResponse.newStatus = (BigInteger) eventValues.getNonIndexedValues().get(1).getValue();
            typedResponse.timestamp = (BigInteger) eventValues.getNonIndexedValues().get(2).getValue();
            responses.add(typedResponse);
        }
        return responses;
    }

    public List<KeyRotatedEventResponse> getKeyRotatedEvents(TransactionReceipt transactionReceipt) {
        List<EventValuesWithLog> valueList = extractEventParametersWithLog(KEYROTATED_EVENT, transactionReceipt);
        ArrayList<KeyRotatedEventResponse> responses = new ArrayList<KeyRotatedEventResponse>(valueList.size());
        for (EventValuesWithLog eventValues : valueList) {
            KeyRotatedEventResponse typedResponse = new KeyRotatedEventResponse();
            typedResponse.log = eventValues.getLog();
            typedResponse.keyId = (BigInteger) eventValues.getIndexedValues().get(0).getValue();
            typedResponse.newVersion = (BigInteger) eventValues.getNonIndexedValues().get(0).getValue();
            typedResponse.status = (BigInteger) eventValues.getNonIndexedValues().get(1).getValue();
            typedResponse.timestamp = (BigInteger) eventValues.getNonIndexedValues().get(2).getValue();
            responses.add(typedResponse);
        }
        return responses;
    }

    public static KeyEvidence load(String contractAddress, Client client, CryptoKeyPair credential) {
        return new KeyEvidence(contractAddress, client, credential);
    }

    public static class UploadSuccessEventResponse {
        public TransactionReceipt.Logs log;
        public BigInteger keyId;
        public BigInteger version;
        public BigInteger status;
        public BigInteger timestamp;
    }

    public static class StatusChangedEventResponse {
        public TransactionReceipt.Logs log;
        public BigInteger keyId;
        public BigInteger version;
        public BigInteger newStatus;
        public BigInteger timestamp;
    }

    public static class KeyRotatedEventResponse {
        public TransactionReceipt.Logs log;
        public BigInteger keyId;
        public BigInteger newVersion;
        public BigInteger status;
        public BigInteger timestamp;
    }
}
