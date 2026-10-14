### 1\. JDK 配置推荐

推荐使用1.8.0_302及以上，建议采用Zulu JDK

### 2\. JAR 包引用

```xml
<!-- 以下四个依赖包不需要在pom中配置，只需要install到本地仓库或者私仓相应位置，相关的jar文件以maven仓库规范文件夹的形式提供，开发者只需复制相应文件夹到对应路径即可 -->
<dependency>
    <groupId>com.yunphant</groupId>
    <artifactId>kms-core</artifactId>
    <version>1.0-DID</version>
</dependency>

<dependency>
    <groupId>org.hyperledger.fabric</groupId>
    <artifactId>fabric-gateway-java-gm</artifactId>
    <version>2.2.0-did-gm-SNAPSHOT</version>
</dependency>

<dependency>
    <groupId>org.hyperledger.fabric-sdk-java</groupId>
    <artifactId>fabric-sdk-java-gm-slf4j</artifactId>
    <version>2.2.13-did</version>
</dependency>

<!-- 该依赖会在本地仓库内创建4个文件夹以及三个jar文件 -->
<dependency>
    <groupId>org.openeuler</groupId>
    <artifactId>bgmprovider</artifactId>
    <version>1.0.3.1-yx</version>
</dependency>

<!-- did-sdk，在pom.xml中配置该dependency。前提是上述的四个依赖包install操作已完成 -->
<dependency>
    <groupId>com.yunphant</groupId>
    <artifactId>did-sdk-gm</artifactId>
    <version>1.1.1</version>
</dependency>
```

### 3\. SDK使用

#### 3.1 fabric.config.properties配置

以maven标准项目为例，需要将fabric.config.properties文件外置到与项目同级的目录下。

如：

项目路径：`<ROOTPATH>/didProject`

配置路径：`<ROOTPATH>/fabric.config.properties`

```properties
 # 网络配置文件路径。根据实际情况修改，参考章节4.1 connection.json
networkConfigPath=D:\\diddemo\\connection.json
 # 用户证书路径，根据实际情况填写
certificatePath=D:\\diddemo\\crypto-config\\did\\peers\\peer-0-did\\msp\\signcerts\\peer-0-did@did-cert.pem
 # 用户私钥路径，根据实际情况填写
privateKeyPath=D:\\diddemo\\crypto-config\\did\\peers\\peer-0-did\\msp\\keystore\\a356de8cfa1cf8c9aea198e5260641f86f96fb68ecb24ccba2fc3ca6364ba4da_sk
# 通道名字，根据实际情况填写，需要和connection.json配置匹配
channelName=didchannel
# 用户名，根据实际情况填写
userName=peer-0-did
# 访问的组织名，根据实际情况填写
mspId=did
# 合约id，根据实际情况填写
chaincodeId=yunidcc
# 过期时间 单位秒
timeOut=10
# 加密算法类型secp256k1/sm2
encryption=sm2
# did生成规范的方法名称，根据实际情况填写
methodId=methodId
```

1.  将上述`path`路径修改为本地证书对应路径
2.  将`connection.json`文件中`path`修改为本地证书对应路径
3.  若上诉`properties`中`channelName`及`mspid`发生变动，则`connection.json`内相关配置也需修改
4.  若链地址发生变动，则`connection.json`中`url`地址需要变更

#### 3.2 config.properties配置

以maven标准项目为例，该配置文件需要存放到项目最外层目录。如：`$project/config.properties`

```properties
com.yunphant.yunchain.sdk.gmsign=true
com.yunphant.yunchain.sdk.gmtls=true
```

- 当使用`secp256k1`算法证书连接区块链网络时值为**false**
- 当使用`sm2`算法证书连接区块链网络时值为**true**

项目启动时需要配置变量

```
-Dorg.hyperledger.fabric.sdk.configuration=config.properties
```

### 4\. 补充说明

#### 4.1 connection.json

> 该参考文件包含2个组织以及其节点配置
> 
> 参照章节4.2证书结构存放

```json
{
  "name": "basic-network",
  "version": "1.0.0",
  "dependencies": {
  },
  "client": {
    "organization": "au",
    "connection": {
      "timeout": {
        "peer": {
          "endorser": "300"
        },
        "orderer": "300"
      }
    }
  },
  "channels": {
    "didchannel": {
      "orderers": [
        "orderer-0-au",
        "orderer-1-au",
        "orderer-2-au",
        "orderer-0-ag"
      ],
      "peers": {
        "peer-0-au": {
          "endorsingPeer": true,
          "chaincodeQuery": true,
          "ledgerQuery": true,
          "eventSource": true
        },
        "peer-0-ag": {
          "endorsingPeer": true,
          "chaincodeQuery": true,
          "ledgerQuery": true,
          "eventSource": true
        }
      }
    },
    "didchannel2": {
      "orderers": [
        "orderer-0-au",
        "orderer-1-au",
        "orderer-2-au",
        "orderer-0-ag"
      ],
      "peers": {
        "peer-0-au": {
          "endorsingPeer": true,
          "chaincodeQuery": true,
          "ledgerQuery": true,
          "eventSource": true
        },
        "peer-0-ag": {
          "endorsingPeer": true,
          "chaincodeQuery": true,
          "ledgerQuery": true,
          "eventSource": true
        }
      }
    }
  },
  "organizations": {
    "au": {
      "mspid": "au",
      "peers": [
        "peer-0-au"
      ],
      "adminPrivateKeyPEM": {
        "path": "/data/crypto-config/peerOrganizations/au/peer-0-au/msp/keystore/18ca79087aa76464edec1daa62940fb90cb8ce7324acb02bd51bd9eb22efe3b8_sk"
      },
      "signedCertPEM": {
        "path": "/data/crypto-config/peerOrganizations/au/peer-0-au/msp/signcerts/peer-0-au@au-cert.pem"
      }
    },
    "ag": {
      "mspid": "ag",
      "peers": [
        "peer-0-ag"
      ],
      "adminPrivateKeyPEM": {
        "path": "/data/crypto-config/peerOrganizations/ag/peer-0-ag/msp/keystore/305e626f130b4f5dabe9d9ed7a8f2cf2954acddbc6875ca00eb572fcd4ee4c9a_sk"
      },
      "signedCertPEM": {
        "path": "/data/crypto-config/peerOrganizations/ag/peer-0-ag/msp/signcerts/peer-0-ag@ag-cert.pem"
      }
    }
  },
  "orderers": {
    "orderer-0-au": {
      "url": "grpcs://192.168.11.143:30004",
      "mspid": "orderer-0-au",
      "grpcOptions": {
        "ssl-target-name-override": "orderer-0-au",
        "hostnameOverride": "orderer-0-au"
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/ordererOrganizations/au/orderer-0-au/tls/ca.crt"
      }
    },
    "orderer-1-au": {
      "url": "grpcs://192.168.11.143:30006",
      "mspid": "orderer-1-au",
      "grpcOptions": {
        "ssl-target-name-override": "orderer-1-au",
        "hostnameOverride": "orderer-1-au"
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/ordererOrganizations/au/orderer-1-au/tls/ca.crt"
      }
    },
    "orderer-2-au": {
      "url": "grpcs://192.168.11.143:30008",
      "mspid": "orderer-2-au",
      "grpcOptions": {
        "ssl-target-name-override": "orderer-2-au",
        "hostnameOverride": "orderer-2-au"
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/ordererOrganizations/au/orderer-2-au/tls/ca.crt"
      }
    },
    "orderer-0-ag": {
      "url": "grpcs://192.168.11.143:30015",
      "mspid": "orderer-0-ag",
      "grpcOptions": {
        "ssl-target-name-override": "orderer-0-ag",
        "hostnameOverride": "orderer-0-ag"
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/ordererOrganizations/ag/orderer-0-ag/tls/ca.crt"
      }
    }
  },
  "peers": {
    "peer-0-au": {
      "url": "grpcs://192.168.11.143:30002",
      "grpcOptions": {
        "ssl-target-name-override": "peer-0-au",
        "hostnameOverride": "peer-0-au",
        "request-timeout": 120001
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/peerOrganizations/au/peer-0-au/tls/ca.crt"
      }
    },
    "peer-0-ag": {
      "url": "grpcs://192.168.11.143:30013",
      "grpcOptions": {
        "ssl-target-name-override": "peer-0-ag",
        "hostnameOverride": "peer-0-ag",
        "request-timeout": 120001
      },
      "tlsCACerts": {
        "path": "/data/crypto-config/peerOrganizations/ag/peer-0-ag/tls/ca.crt"
      }
    }
  }
}
```

#### 4.2 证书结构

```
data/
├── connection.json
└── crypto-config
    ├── ordererOrganizations
    │   ├── ag
    │   │   └── orderer-0-ag
    │   │       ├── msp
    │   │       │   ├── admincerts
    │   │       │   │   └── Admin@ag-cert.pem
    │   │       │   ├── cacerts
    │   │       │   │   └── ag-cert.pem
    │   │       │   ├── keystore
    │   │       │   │   └── 165b469d266d8cd886e51f0424931d5f02262df0b96d54664c3e1468361d7088_sk
    │   │       │   ├── signcerts
    │   │       │   │   └── orderer-0-ag@ag-cert.pem
    │   │       │   └── tlscacerts
    │   │       │       └── ag-cert.pem
    │   │       └── tls
    │   │           ├── ca.crt
    │   │           ├── server.crt
    │   │           ├── serverenc.crt
    │   │           ├── serverenc.key
    │   │           └── server.key
    │   └── au
    │       ├── orderer-0-au
    │       │   ├── msp
    │       │   │   ├── admincerts
    │       │   │   │   └── Admin@au-cert.pem
    │       │   │   ├── cacerts
    │       │   │   │   └── au-cert.pem
    │       │   │   ├── keystore
    │       │   │   │   └── 9fd39b93c99755ccafe0517bbda2bb522a2b1c2d982cdc95fbfd96599527c02c_sk
    │       │   │   ├── signcerts
    │       │   │   │   └── orderer-0-au@au-cert.pem
    │       │   │   └── tlscacerts
    │       │   │       └── au-cert.pem
    │       │   └── tls
    │       │       ├── ca.crt
    │       │       ├── server.crt
    │       │       ├── serverenc.crt
    │       │       ├── serverenc.key
    │       │       └── server.key
    │       ├── orderer-1-au
    │       │   ├── msp
    │       │   │   ├── admincerts
    │       │   │   │   └── Admin@au-cert.pem
    │       │   │   ├── cacerts
    │       │   │   │   └── au-cert.pem
    │       │   │   ├── keystore
    │       │   │   │   └── a36276c021ca1e7fb3c84c820f0662811501dae094e2b3bb76314930a8a57e6e_sk
    │       │   │   ├── signcerts
    │       │   │   │   └── orderer-1-au@au-cert.pem
    │       │   │   └── tlscacerts
    │       │   │       └── au-cert.pem
    │       │   └── tls
    │       │       ├── ca.crt
    │       │       ├── server.crt
    │       │       ├── serverenc.crt
    │       │       ├── serverenc.key
    │       │       └── server.key
    │       └── orderer-2-au
    │           ├── msp
    │           │   ├── admincerts
    │           │   │   └── Admin@au-cert.pem
    │           │   ├── cacerts
    │           │   │   └── au-cert.pem
    │           │   ├── keystore
    │           │   │   └── 0e02038c2ebc38274bf03fa46feeb241a1210c5e444c1229a7972c8a6104a0b4_sk
    │           │   ├── signcerts
    │           │   │   └── orderer-2-au@au-cert.pem
    │           │   └── tlscacerts
    │           │       └── au-cert.pem
    │           └── tls
    │               ├── ca.crt
    │               ├── server.crt
    │               ├── serverenc.crt
    │               ├── serverenc.key
    │               └── server.key
    └── peerOrganizations
        ├── ag
        │   └── peer-0-ag
        │       ├── msp
        │       │   ├── admincerts
        │       │   │   └── Admin@ag-cert.pem
        │       │   ├── cacerts
        │       │   │   └── ag-cert.pem
        │       │   ├── keystore
        │       │   │   └── 305e626f130b4f5dabe9d9ed7a8f2cf2954acddbc6875ca00eb572fcd4ee4c9a_sk
        │       │   ├── signcerts
        │       │   │   └── peer-0-ag@ag-cert.pem
        │       │   └── tlscacerts
        │       │       └── ag-cert.pem
        │       └── tls
        │           ├── ca.crt
        │           ├── server.crt
        │           ├── serverenc.crt
        │           ├── serverenc.key
        │           └── server.key
        └── au
            └── peer-0-au
                ├── msp
                │   ├── admincerts
                │   │   └── Admin@au-cert.pem
                │   ├── cacerts
                │   │   └── au-cert.pem
                │   ├── keystore
                │   │   └── 18ca79087aa76464edec1daa62940fb90cb8ce7324acb02bd51bd9eb22efe3b8_sk
                │   ├── signcerts
                │   │   └── peer-0-au@au-cert.pem
                │   └── tlscacerts
                │       └── au-cert.pem
                └── tls
                    ├── ca.crt
                    ├── server.crt
                    ├── serverenc.crt
                    ├── serverenc.key
                    └── server.key
```