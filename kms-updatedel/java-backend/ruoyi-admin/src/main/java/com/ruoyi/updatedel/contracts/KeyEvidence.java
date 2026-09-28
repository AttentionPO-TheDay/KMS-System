package com.ruoyi.updatedel.contracts;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.fisco.bcos.sdk.abi.FunctionReturnDecoder;
import org.fisco.bcos.sdk.abi.TypeReference;
import org.fisco.bcos.sdk.abi.datatypes.Address;
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
import org.fisco.bcos.sdk.abi.datatypes.generated.tuples.generated.Tuple5;
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
    public static final String[] BINARY_ARRAY = {"608060405234801561001057600080fd5b50336000806101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055506113b8806100606000396000f30060806040526004361061006d576000357c0100000000000000000000000000000000000000000000000000000000900463ffffffff1680631c80786d146100725780634b3765e2146100c057806389a40913146102355780638da5cb5b14610358578063de07c334146103af575b600080fd5b34801561007e57600080fd5b506100aa60048036038101908080359060200190929190803560ff169060200190929190505050610446565b6040518082815260200191505060405180910390f35b3480156100cc57600080fd5b5061021f60048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803515159060200190929190803563ffffffff16906020019092919050505061078b565b6040518082815260200191505060405180910390f35b34801561024157600080fd5b50610342600480360381019080803590602001908201803590602001908080601f016020809104026020016040519081016040528093929190818152602001838380828437820191505050505050919291929080359060200190929190803563ffffffff169060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290505050610ba2565b6040518082815260200191505060405180910390f35b34801561036457600080fd5b5061036d610e81565b604051808273ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200191505060405180910390f35b3480156103bb57600080fd5b5061043060048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803563ffffffff169060200190929190505050610ea6565b6040518082815260200191505060405180910390f35b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff1614151561050c576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b600060016000858152602001908152602001600020600001541415151561059b576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579206d697373696e6700000000000000000000000000000000000000000081525060200191505060405180910390fd5b6105a482611256565b1515610618576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600e8152602001807f696e76616c69642073746174757300000000000000000000000000000000000081525060200191505060405180910390fd5b60036001600085815260200190815260200160002060050160019054906101000a900460ff1660ff16141515156106b7576040517f08c379a00000000000000000000000000000000000000000000000000000000081526004018080602001828103825260118152602001807f7265766f6b656420696d6d757461626c6500000000000000000000000000000081525060200191505060405180910390fd5b816001600085815260200190815260200160002060050160016101000a81548160ff021916908360ff160217905550426001600085815260200190815260200160002060070181905550827f70cb641a641a32625eadf519ca27bf0c1fb9b6784fea5bb08c209f5d184d6f796001600086815260200190815260200160002060080160009054906101000a900463ffffffff168442604051808463ffffffff1663ffffffff1681526020018360ff1660ff168152602001828152602001935050505060405180910390a26000905092915050565b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610851576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b600088141515156108ca576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600d8152602001807f696e76616c6964206b657949640000000000000000000000000000000000000081525060200191505060405180910390fd5b60008263ffffffff16111515610948576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600f8152602001807f696e76616c69642076657273696f6e000000000000000000000000000000000081525060200191505060405180910390fd5b6000600160008a8152602001908152602001600020600001541415156109d6576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6b6579206578697374730000000000000000000000000000000000000000000081525060200191505060405180910390fd5b610140604051908101604052808981526020018881526020018781526020018681526020018581526020018415158152602001600060ff1681526020014281526020014281526020018363ffffffff16815250600160008a8152602001908152602001600020600082015181600001556020820151816001019080519060200190610a62929190611267565b506040820151816002019080519060200190610a7f929190611267565b506060820151816003019080519060200190610a9c929190611267565b506080820151816004019080519060200190610ab9929190611267565b5060a08201518160050160006101000a81548160ff02191690831515021790555060c08201518160050160016101000a81548160ff021916908360ff16021790555060e0820151816006015561010082015181600701556101208201518160080160006101000a81548163ffffffff021916908363ffffffff160217905550905050877ff7c7174d027f6e78989ea7059ca9db0470f01e96d1078a63dd91fcfe3092ab6b83600042604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a260009050979650505050505050565b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610c68576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b60008651111515610ce1576040517f08c379a00000000000000000000000000000000000000000000000000000000081526004018080602001828103825260138152602001807f6576656e7420747970652072657175697265640000000000000000000000000081525060200191505060405180910390fd5b847f22de73619d629ec7133d447cdf4518a474ff2e04167d013fe27d8ae0022716b0878686864260405180806020018663ffffffff1663ffffffff1681526020018060200180602001858152602001848103845289818151815260200191508051906020019080838360005b83811015610d68578082015181840152602081019050610d4d565b50505050905090810190601f168015610d955780820380516001836020036101000a031916815260200191505b50848103835287818151815260200191508051906020019080838360005b83811015610dce578082015181840152602081019050610db3565b50505050905090810190601f168015610dfb5780820380516001836020036101000a031916815260200191505b50848103825286818151815260200191508051906020019080838360005b83811015610e34578082015181840152602081019050610e19565b50505050905090810190601f168015610e615780820380516001836020036101000a031916815260200191505b509850505050505050505060405180910390a26000905095945050505050565b6000809054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b6000806000809054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610f6d576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b6001600086815260200190815260200160002090506000816000015414151515610fff576040517f08c379a0000000000000","00000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579206d697373696e6700000000000000000000000000000000000000000081525060200191505060405180910390fd5b60038160050160019054906101000a900460ff1660ff161415151561108c576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579207265766f6b656400000000000000000000000000000000000000000081525060200191505060405180910390fd5b8060080160009054906101000a900463ffffffff1663ffffffff168363ffffffff16111515611123576040517f08c379a00000000000000000000000000000000000000000000000000000000081526004018080602001828103825260158152602001807f76657273696f6e206d75737420696e637265617365000000000000000000000081525060200191505060405180910390fd5b847f70cb641a641a32625eadf519ca27bf0c1fb9b6784fea5bb08c209f5d184d6f798260080160009054906101000a900463ffffffff16600242604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a2838160020190805190602001906111a79291906112e7565b50828160080160006101000a81548163ffffffff021916908363ffffffff16021790555060008160050160016101000a81548160ff021916908360ff160217905550428160070181905550847f5b3bf0f6779522e07e311f2105bd7d5804ca3dc1115ae12408cac41b1e22a9be84600042604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a260009150509392505050565b600060038260ff1611159050919050565b828054600181600116156101000203166002900490600052602060002090601f016020900481019282601f106112a857805160ff19168380011785556112d6565b828001600101855582156112d6579182015b828111156112d55782518255916020019190600101906112ba565b5b5090506112e39190611367565b5090565b828054600181600116156101000203166002900490600052602060002090601f016020900481019282601f1061132857805160ff1916838001178555611356565b82800160010185558215611356579182015b8281111561135557825182559160200191906001019061133a565b5b5090506113639190611367565b5090565b61138991905b8082111561138557600081600090555060010161136d565b5090565b905600a165627a7a72305820d2121a3ba349f8c82e6c847e539ef1f18fff70a2b055cc69a452f8dbee5aab730029"};

    public static final String BINARY = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", BINARY_ARRAY);

    public static final String[] SM_BINARY_ARRAY = {"608060405234801561001057600080fd5b50336000806101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055506113b8806100606000396000f30060806040526004361061006d576000357c0100000000000000000000000000000000000000000000000000000000900463ffffffff1680635089e2c814610072578063764d5d9f146100c9578063b5787379146101ec578063f84daa7a14610361578063f9b7c3b9146103af575b600080fd5b34801561007e57600080fd5b50610087610446565b604051808273ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200191505060405180910390f35b3480156100d557600080fd5b506101d6600480360381019080803590602001908201803590602001908080601f016020809104026020016040519081016040528093929190818152602001838380828437820191505050505050919291929080359060200190929190803563ffffffff169060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f016020809104026020016040519081016040528093929190818152602001838380828437820191505050505050919291929050505061046b565b6040518082815260200191505060405180910390f35b3480156101f857600080fd5b5061034b60048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803515159060200190929190803563ffffffff16906020019092919050505061074a565b6040518082815260200191505060405180910390f35b34801561036d57600080fd5b5061039960048036038101908080359060200190929190803560ff169060200190929190505050610b61565b6040518082815260200191505060405180910390f35b3480156103bb57600080fd5b5061043060048036038101908080359060200190929190803590602001908201803590602001908080601f0160208091040260200160405190810160405280939291908181526020018383808284378201915050505050509192919290803563ffffffff169060200190929190505050610ea6565b6040518082815260200191505060405180910390f35b6000809054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610531576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b600086511115156105aa576040517fc703cb120000000000000000000000000000000000000000000000000000000081526004018080602001828103825260138152602001807f6576656e7420747970652072657175697265640000000000000000000000000081525060200191505060405180910390fd5b847f8af2766a189d071bb667b92e95f12edcb4a0e49fe562aef6c5a804b96f0127ef878686864260405180806020018663ffffffff1663ffffffff1681526020018060200180602001858152602001848103845289818151815260200191508051906020019080838360005b83811015610631578082015181840152602081019050610616565b50505050905090810190601f16801561065e5780820380516001836020036101000a031916815260200191505b50848103835287818151815260200191508051906020019080838360005b8381101561069757808201518184015260208101905061067c565b50505050905090810190601f1680156106c45780820380516001836020036101000a031916815260200191505b50848103825286818151815260200191508051906020019080838360005b838110156106fd5780820151818401526020810190506106e2565b50505050905090810190601f16801561072a5780820380516001836020036101000a031916815260200191505b509850505050505050505060405180910390a26000905095945050505050565b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610810576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b60008814151515610889576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600d8152602001807f696e76616c6964206b657949640000000000000000000000000000000000000081525060200191505060405180910390fd5b60008263ffffffff16111515610907576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600f8152602001807f696e76616c69642076657273696f6e000000000000000000000000000000000081525060200191505060405180910390fd5b6000600160008a815260200190815260200160002060000154141515610995576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6b6579206578697374730000000000000000000000000000000000000000000081525060200191505060405180910390fd5b610140604051908101604052808981526020018881526020018781526020018681526020018581526020018415158152602001600060ff1681526020014281526020014281526020018363ffffffff16815250600160008a8152602001908152602001600020600082015181600001556020820151816001019080519060200190610a21929190611267565b506040820151816002019080519060200190610a3e929190611267565b506060820151816003019080519060200190610a5b929190611267565b506080820151816004019080519060200190610a78929190611267565b5060a08201518160050160006101000a81548160ff02191690831515021790555060c08201518160050160016101000a81548160ff021916908360ff16021790555060e0820151816006015561010082015181600701556101208201518160080160006101000a81548163ffffffff021916908363ffffffff160217905550905050877f6c3489fecf892c412198f9bdb97ac5083084b5a591550176710c6d6190ac0d0983600042604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a260009050979650505050505050565b60008060009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610c27576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b6000600160008581526020019081526020016000206000015414151515610cb6576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579206d697373696e6700000000000000000000000000000000000000000081525060200191505060405180910390fd5b610cbf82611256565b1515610d33576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600e8152602001807f696e76616c69642073746174757300000000000000000000000000000000000081525060200191505060405180910390fd5b60036001600085815260200190815260200160002060050160019054906101000a900460ff1660ff1614151515610dd2576040517fc703cb120000000000000000000000000000000000000000000000000000000081526004018080602001828103825260118152602001807f7265766f6b656420696d6d757461626c6500000000000000000000000000000081525060200191505060405180910390fd5b816001600085815260200190815260200160002060050160016101000a81548160ff021916908360ff160217905550426001600085815260200190815260200160002060070181905550827f07647d2ab63845a0f76961cc516f64a05398c825dfd231eb87d2c1618693b1126001600086815260200190815260200160002060080160009054906101000a900463ffffffff168442604051808463ffffffff1663ffffffff1681526020018360ff1660ff168152602001828152602001935050505060405180910390a26000905092915050565b6000806000809054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff16141515610f6d576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600a8152602001807f6f6e6c79206f776e65720000000000000000000000000000000000000000000081525060200191505060405180910390fd5b6001600086815260200190815260200160002090506000816000015414151515610fff576040517fc703cb12000000000000","00000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579206d697373696e6700000000000000000000000000000000000000000081525060200191505060405180910390fd5b60038160050160019054906101000a900460ff1660ff161415151561108c576040517fc703cb1200000000000000000000000000000000000000000000000000000000815260040180806020018281038252600b8152602001807f6b6579207265766f6b656400000000000000000000000000000000000000000081525060200191505060405180910390fd5b8060080160009054906101000a900463ffffffff1663ffffffff168363ffffffff16111515611123576040517fc703cb120000000000000000000000000000000000000000000000000000000081526004018080602001828103825260158152602001807f76657273696f6e206d75737420696e637265617365000000000000000000000081525060200191505060405180910390fd5b847f07647d2ab63845a0f76961cc516f64a05398c825dfd231eb87d2c1618693b1128260080160009054906101000a900463ffffffff16600242604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a2838160020190805190602001906111a79291906112e7565b50828160080160006101000a81548163ffffffff021916908363ffffffff16021790555060008160050160016101000a81548160ff021916908360ff160217905550428160070181905550847f2f34d6787b90ac3e15a6dbd5203593276cf4297ce5e45350586c2ac26e18eed684600042604051808463ffffffff1663ffffffff1681526020018360ff168152602001828152602001935050505060405180910390a260009150509392505050565b600060038260ff1611159050919050565b828054600181600116156101000203166002900490600052602060002090601f016020900481019282601f106112a857805160ff19168380011785556112d6565b828001600101855582156112d6579182015b828111156112d55782518255916020019190600101906112ba565b5b5090506112e39190611367565b5090565b828054600181600116156101000203166002900490600052602060002090601f016020900481019282601f1061132857805160ff1916838001178555611356565b82800160010185558215611356579182015b8281111561135557825182559160200191906001019061133a565b5b5090506113639190611367565b5090565b61138991905b8082111561138557600081600090555060010161136d565b5090565b905600a165627a7a72305820446f1c634f3f56fc0c6cf01e47af9e0ed119bc1fcdcafdd65e2e420a07ba685a0029"};

    public static final String SM_BINARY = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", SM_BINARY_ARRAY);

    public static final String[] ABI_ARRAY = {"[{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_newStatus\",\"type\":\"uint8\"}],\"name\":\"changeKeyStatus\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_username\",\"type\":\"string\"},{\"name\":\"_pubKey\",\"type\":\"string\"},{\"name\":\"_algo\",\"type\":\"string\"},{\"name\":\"_usage\",\"type\":\"string\"},{\"name\":\"_isAutoUpdate\",\"type\":\"bool\"},{\"name\":\"_version\",\"type\":\"uint32\"}],\"name\":\"uploadKey\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"constant\":false,\"inputs\":[{\"name\":\"_eventType\",\"type\":\"string\"},{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_version\",\"type\":\"uint32\"},{\"name\":\"_nodeId\",\"type\":\"string\"},{\"name\":\"_publicMaterialHash\",\"type\":\"string\"}],\"name\":\"recordEvent\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"constant\":true,\"inputs\":[],\"name\":\"owner\",\"outputs\":[{\"name\":\"\",\"type\":\"address\"}],\"payable\":false,\"stateMutability\":\"view\",\"type\":\"function\"},{\"constant\":false,\"inputs\":[{\"name\":\"_keyId\",\"type\":\"uint256\"},{\"name\":\"_newPubKey\",\"type\":\"string\"},{\"name\":\"_newVersion\",\"type\":\"uint32\"}],\"name\":\"rotateKey\",\"outputs\":[{\"name\":\"\",\"type\":\"int256\"}],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"function\"},{\"inputs\":[],\"payable\":false,\"stateMutability\":\"nonpayable\",\"type\":\"constructor\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"version\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"status\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"UploadSuccess\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"version\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"newStatus\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"StatusChanged\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"newVersion\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"status\",\"type\":\"uint8\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"KeyRotated\",\"type\":\"event\"},{\"anonymous\":false,\"inputs\":[{\"indexed\":false,\"name\":\"eventType\",\"type\":\"string\"},{\"indexed\":true,\"name\":\"keyId\",\"type\":\"uint256\"},{\"indexed\":false,\"name\":\"version\",\"type\":\"uint32\"},{\"indexed\":false,\"name\":\"nodeId\",\"type\":\"string\"},{\"indexed\":false,\"name\":\"publicMaterialHash\",\"type\":\"string\"},{\"indexed\":false,\"name\":\"timestamp\",\"type\":\"uint256\"}],\"name\":\"KeyLifecycleEvent\",\"type\":\"event\"}]"};

    public static final String ABI = org.fisco.bcos.sdk.utils.StringUtils.joinAll("", ABI_ARRAY);

    public static final String FUNC_CHANGEKEYSTATUS = "changeKeyStatus";

    public static final String FUNC_UPLOADKEY = "uploadKey";

    public static final String FUNC_RECORDEVENT = "recordEvent";

    public static final String FUNC_OWNER = "owner";

    public static final String FUNC_ROTATEKEY = "rotateKey";

    public static final Event UPLOADSUCCESS_EVENT = new Event("UploadSuccess", 
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));
    ;

    public static final Event STATUSCHANGED_EVENT = new Event("StatusChanged", 
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));
    ;

    public static final Event KEYROTATED_EVENT = new Event("KeyRotated", 
            Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Uint8>() {}, new TypeReference<Uint256>() {}));
    ;

    public static final Event KEYLIFECYCLEEVENT_EVENT = new Event("KeyLifecycleEvent", 
            Arrays.<TypeReference<?>>asList(new TypeReference<Utf8String>() {}, new TypeReference<Uint256>(true) {}, new TypeReference<Uint32>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Uint256>() {}));
    ;

    protected KeyEvidence(String contractAddress, Client client, CryptoKeyPair credential) {
        super(getBinary(client.getCryptoSuite()), contractAddress, client, credential);
    }

    public static String getBinary(CryptoSuite cryptoSuite) {
        return (cryptoSuite.getCryptoTypeConfig() == CryptoType.ECDSA_TYPE ? BINARY : SM_BINARY);
    }

    public TransactionReceipt changeKeyStatus(BigInteger _keyId, BigInteger _newStatus) {
        final Function function = new Function(
                FUNC_CHANGEKEYSTATUS, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint8(_newStatus)), 
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public byte[] changeKeyStatus(BigInteger _keyId, BigInteger _newStatus, TransactionCallback callback) {
        final Function function = new Function(
                FUNC_CHANGEKEYSTATUS, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint8(_newStatus)), 
                Collections.<TypeReference<?>>emptyList());
        return asyncExecuteTransaction(function, callback);
    }

    public String getSignedTransactionForChangeKeyStatus(BigInteger _keyId, BigInteger _newStatus) {
        final Function function = new Function(
                FUNC_CHANGEKEYSTATUS, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint8(_newStatus)), 
                Collections.<TypeReference<?>>emptyList());
        return createSignedTransaction(function);
    }

    public Tuple2<BigInteger, BigInteger> getChangeKeyStatusInput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getInput().substring(10);
        final Function function = new Function(FUNC_CHANGEKEYSTATUS, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>() {}, new TypeReference<Uint8>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple2<BigInteger, BigInteger>(

                (BigInteger) results.get(0).getValue(), 
                (BigInteger) results.get(1).getValue()
                );
    }

    public Tuple1<BigInteger> getChangeKeyStatusOutput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getOutput();
        final Function function = new Function(FUNC_CHANGEKEYSTATUS, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Int256>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple1<BigInteger>(

                (BigInteger) results.get(0).getValue()
                );
    }

    public TransactionReceipt uploadKey(BigInteger _keyId, String _username, String _pubKey, String _algo, String _usage, Boolean _isAutoUpdate, BigInteger _version) {
        final Function function = new Function(
                FUNC_UPLOADKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_username), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_pubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_algo), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_usage), 
                new org.fisco.bcos.sdk.abi.datatypes.Bool(_isAutoUpdate), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version)), 
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public byte[] uploadKey(BigInteger _keyId, String _username, String _pubKey, String _algo, String _usage, Boolean _isAutoUpdate, BigInteger _version, TransactionCallback callback) {
        final Function function = new Function(
                FUNC_UPLOADKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_username), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_pubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_algo), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_usage), 
                new org.fisco.bcos.sdk.abi.datatypes.Bool(_isAutoUpdate), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version)), 
                Collections.<TypeReference<?>>emptyList());
        return asyncExecuteTransaction(function, callback);
    }

    public String getSignedTransactionForUploadKey(BigInteger _keyId, String _username, String _pubKey, String _algo, String _usage, Boolean _isAutoUpdate, BigInteger _version) {
        final Function function = new Function(
                FUNC_UPLOADKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_username), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_pubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_algo), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_usage), 
                new org.fisco.bcos.sdk.abi.datatypes.Bool(_isAutoUpdate), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version)), 
                Collections.<TypeReference<?>>emptyList());
        return createSignedTransaction(function);
    }

    public Tuple7<BigInteger, String, String, String, String, Boolean, BigInteger> getUploadKeyInput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getInput().substring(10);
        final Function function = new Function(FUNC_UPLOADKEY, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Bool>() {}, new TypeReference<Uint32>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple7<BigInteger, String, String, String, String, Boolean, BigInteger>(

                (BigInteger) results.get(0).getValue(), 
                (String) results.get(1).getValue(), 
                (String) results.get(2).getValue(), 
                (String) results.get(3).getValue(), 
                (String) results.get(4).getValue(), 
                (Boolean) results.get(5).getValue(), 
                (BigInteger) results.get(6).getValue()
                );
    }

    public Tuple1<BigInteger> getUploadKeyOutput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getOutput();
        final Function function = new Function(FUNC_UPLOADKEY, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Int256>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple1<BigInteger>(

                (BigInteger) results.get(0).getValue()
                );
    }

    public TransactionReceipt recordEvent(String _eventType, BigInteger _keyId, BigInteger _version, String _nodeId, String _publicMaterialHash) {
        final Function function = new Function(
                FUNC_RECORDEVENT, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_eventType), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_nodeId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_publicMaterialHash)), 
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public byte[] recordEvent(String _eventType, BigInteger _keyId, BigInteger _version, String _nodeId, String _publicMaterialHash, TransactionCallback callback) {
        final Function function = new Function(
                FUNC_RECORDEVENT, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_eventType), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_nodeId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_publicMaterialHash)), 
                Collections.<TypeReference<?>>emptyList());
        return asyncExecuteTransaction(function, callback);
    }

    public String getSignedTransactionForRecordEvent(String _eventType, BigInteger _keyId, BigInteger _version, String _nodeId, String _publicMaterialHash) {
        final Function function = new Function(
                FUNC_RECORDEVENT, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_eventType), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_version), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_nodeId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_publicMaterialHash)), 
                Collections.<TypeReference<?>>emptyList());
        return createSignedTransaction(function);
    }

    public Tuple5<String, BigInteger, BigInteger, String, String> getRecordEventInput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getInput().substring(10);
        final Function function = new Function(FUNC_RECORDEVENT, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Utf8String>() {}, new TypeReference<Uint256>() {}, new TypeReference<Uint32>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Utf8String>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple5<String, BigInteger, BigInteger, String, String>(

                (String) results.get(0).getValue(), 
                (BigInteger) results.get(1).getValue(), 
                (BigInteger) results.get(2).getValue(), 
                (String) results.get(3).getValue(), 
                (String) results.get(4).getValue()
                );
    }

    public Tuple1<BigInteger> getRecordEventOutput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getOutput();
        final Function function = new Function(FUNC_RECORDEVENT, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Int256>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple1<BigInteger>(

                (BigInteger) results.get(0).getValue()
                );
    }

    public String owner() throws ContractException {
        final Function function = new Function(FUNC_OWNER, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Address>() {}));
        return executeCallWithSingleValueReturn(function, String.class);
    }

    public TransactionReceipt rotateKey(BigInteger _keyId, String _newPubKey, BigInteger _newVersion) {
        final Function function = new Function(
                FUNC_ROTATEKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_newPubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_newVersion)), 
                Collections.<TypeReference<?>>emptyList());
        return executeTransaction(function);
    }

    public byte[] rotateKey(BigInteger _keyId, String _newPubKey, BigInteger _newVersion, TransactionCallback callback) {
        final Function function = new Function(
                FUNC_ROTATEKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_newPubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_newVersion)), 
                Collections.<TypeReference<?>>emptyList());
        return asyncExecuteTransaction(function, callback);
    }

    public String getSignedTransactionForRotateKey(BigInteger _keyId, String _newPubKey, BigInteger _newVersion) {
        final Function function = new Function(
                FUNC_ROTATEKEY, 
                Arrays.<Type>asList(new org.fisco.bcos.sdk.abi.datatypes.generated.Uint256(_keyId), 
                new org.fisco.bcos.sdk.abi.datatypes.Utf8String(_newPubKey), 
                new org.fisco.bcos.sdk.abi.datatypes.generated.Uint32(_newVersion)), 
                Collections.<TypeReference<?>>emptyList());
        return createSignedTransaction(function);
    }

    public Tuple3<BigInteger, String, BigInteger> getRotateKeyInput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getInput().substring(10);
        final Function function = new Function(FUNC_ROTATEKEY, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Uint256>() {}, new TypeReference<Utf8String>() {}, new TypeReference<Uint32>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple3<BigInteger, String, BigInteger>(

                (BigInteger) results.get(0).getValue(), 
                (String) results.get(1).getValue(), 
                (BigInteger) results.get(2).getValue()
                );
    }

    public Tuple1<BigInteger> getRotateKeyOutput(TransactionReceipt transactionReceipt) {
        String data = transactionReceipt.getOutput();
        final Function function = new Function(FUNC_ROTATEKEY, 
                Arrays.<Type>asList(), 
                Arrays.<TypeReference<?>>asList(new TypeReference<Int256>() {}));
        List<Type> results = FunctionReturnDecoder.decode(data, function.getOutputParameters());
        return new Tuple1<BigInteger>(

                (BigInteger) results.get(0).getValue()
                );
    }

    public List<UploadSuccessEventResponse> getUploadSuccessEvents(TransactionReceipt transactionReceipt) {
        List<Contract.EventValuesWithLog> valueList = extractEventParametersWithLog(UPLOADSUCCESS_EVENT, transactionReceipt);
        ArrayList<UploadSuccessEventResponse> responses = new ArrayList<UploadSuccessEventResponse>(valueList.size());
        for (Contract.EventValuesWithLog eventValues : valueList) {
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

    public void subscribeUploadSuccessEvent(String fromBlock, String toBlock, List<String> otherTopics, EventCallback callback) {
        String topic0 = eventEncoder.encode(UPLOADSUCCESS_EVENT);
        subscribeEvent(ABI,BINARY,topic0,fromBlock,toBlock,otherTopics,callback);
    }

    public void subscribeUploadSuccessEvent(EventCallback callback) {
        String topic0 = eventEncoder.encode(UPLOADSUCCESS_EVENT);
        subscribeEvent(ABI,BINARY,topic0,callback);
    }

    public List<StatusChangedEventResponse> getStatusChangedEvents(TransactionReceipt transactionReceipt) {
        List<Contract.EventValuesWithLog> valueList = extractEventParametersWithLog(STATUSCHANGED_EVENT, transactionReceipt);
        ArrayList<StatusChangedEventResponse> responses = new ArrayList<StatusChangedEventResponse>(valueList.size());
        for (Contract.EventValuesWithLog eventValues : valueList) {
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

    public void subscribeStatusChangedEvent(String fromBlock, String toBlock, List<String> otherTopics, EventCallback callback) {
        String topic0 = eventEncoder.encode(STATUSCHANGED_EVENT);
        subscribeEvent(ABI,BINARY,topic0,fromBlock,toBlock,otherTopics,callback);
    }

    public void subscribeStatusChangedEvent(EventCallback callback) {
        String topic0 = eventEncoder.encode(STATUSCHANGED_EVENT);
        subscribeEvent(ABI,BINARY,topic0,callback);
    }

    public List<KeyRotatedEventResponse> getKeyRotatedEvents(TransactionReceipt transactionReceipt) {
        List<Contract.EventValuesWithLog> valueList = extractEventParametersWithLog(KEYROTATED_EVENT, transactionReceipt);
        ArrayList<KeyRotatedEventResponse> responses = new ArrayList<KeyRotatedEventResponse>(valueList.size());
        for (Contract.EventValuesWithLog eventValues : valueList) {
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

    public void subscribeKeyRotatedEvent(String fromBlock, String toBlock, List<String> otherTopics, EventCallback callback) {
        String topic0 = eventEncoder.encode(KEYROTATED_EVENT);
        subscribeEvent(ABI,BINARY,topic0,fromBlock,toBlock,otherTopics,callback);
    }

    public void subscribeKeyRotatedEvent(EventCallback callback) {
        String topic0 = eventEncoder.encode(KEYROTATED_EVENT);
        subscribeEvent(ABI,BINARY,topic0,callback);
    }

    public List<KeyLifecycleEventEventResponse> getKeyLifecycleEventEvents(TransactionReceipt transactionReceipt) {
        List<Contract.EventValuesWithLog> valueList = extractEventParametersWithLog(KEYLIFECYCLEEVENT_EVENT, transactionReceipt);
        ArrayList<KeyLifecycleEventEventResponse> responses = new ArrayList<KeyLifecycleEventEventResponse>(valueList.size());
        for (Contract.EventValuesWithLog eventValues : valueList) {
            KeyLifecycleEventEventResponse typedResponse = new KeyLifecycleEventEventResponse();
            typedResponse.log = eventValues.getLog();
            typedResponse.keyId = (BigInteger) eventValues.getIndexedValues().get(0).getValue();
            typedResponse.eventType = (String) eventValues.getNonIndexedValues().get(0).getValue();
            typedResponse.version = (BigInteger) eventValues.getNonIndexedValues().get(1).getValue();
            typedResponse.nodeId = (String) eventValues.getNonIndexedValues().get(2).getValue();
            typedResponse.publicMaterialHash = (String) eventValues.getNonIndexedValues().get(3).getValue();
            typedResponse.timestamp = (BigInteger) eventValues.getNonIndexedValues().get(4).getValue();
            responses.add(typedResponse);
        }
        return responses;
    }

    public void subscribeKeyLifecycleEventEvent(String fromBlock, String toBlock, List<String> otherTopics, EventCallback callback) {
        String topic0 = eventEncoder.encode(KEYLIFECYCLEEVENT_EVENT);
        subscribeEvent(ABI,BINARY,topic0,fromBlock,toBlock,otherTopics,callback);
    }

    public void subscribeKeyLifecycleEventEvent(EventCallback callback) {
        String topic0 = eventEncoder.encode(KEYLIFECYCLEEVENT_EVENT);
        subscribeEvent(ABI,BINARY,topic0,callback);
    }

    public static KeyEvidence load(String contractAddress, Client client, CryptoKeyPair credential) {
        return new KeyEvidence(contractAddress, client, credential);
    }

    public static KeyEvidence deploy(Client client, CryptoKeyPair credential) throws ContractException {
        return deploy(KeyEvidence.class, client, credential, getBinary(client.getCryptoSuite()), "");
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

    public static class KeyLifecycleEventEventResponse {
        public TransactionReceipt.Logs log;

        public BigInteger keyId;

        public String eventType;

        public BigInteger version;

        public String nodeId;

        public String publicMaterialHash;

        public BigInteger timestamp;
    }
}
