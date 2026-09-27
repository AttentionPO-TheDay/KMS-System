// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title FalconKDS
 * @dev 后量子Falcon无证书密钥分发系统智能合约
 */
contract FalconKDS {
    
    struct NodeInfo {
        string nodeId;
        string name;
        string ipAddress;
        uint256 port;
        bytes kyberPublicKey;
        bytes falconPublicKey;
        string kyberPublicKeyHash;   // 新增：Kyber公钥哈希值
        string falconPublicKeyHash;  // 新增：Falcon公钥哈希值
        bool isActive;
        uint256 registrationTime;
        uint256 lastUpdateTime;
    }
    
    struct KeyExchangeRecord {
        string sessionId;
        string fromNodeId;
        string toNodeId;
        bytes encryptedSessionKey;
        bytes signature;
        uint256 timestamp;
        bool isValid;
    }

    struct MessageRecord {
        string messageId;
        string sessionId;
        string senderNodeId;
        string receiverNodeId;
        string ciphertextHash;
        string algorithm;
        uint256 timestamp;
    }

    // 存储节点信息
    mapping(string => NodeInfo) public nodes;
    mapping(address => string) public addressToNodeId;

    // 存储密钥交换记录
    mapping(string => KeyExchangeRecord) public keyExchanges;

    // 存储消息记录
    mapping(string => MessageRecord) public messageRecords;
    string[] public messageList;

    // 节点列表
    string[] public nodeList;

    // 事件定义
    event NodeRegistered(string indexed nodeId, string name, address indexed nodeAddress);
    event KyberKeyUploaded(string indexed nodeId, bytes kyberPublicKey);
    event FalconKeyUploaded(string indexed nodeId, bytes falconPublicKey);
    event KyberKeyHashUploaded(string indexed nodeId, string publicKeyHash);
    event FalconKeyHashUploaded(string indexed nodeId, string publicKeyHash);
    event SessionKeyExchanged(string indexed sessionId, string fromNodeId, string toNodeId);
    event NodeStatusChanged(string indexed nodeId, bool isActive);
    event MessageRecorded(string indexed messageId, string sessionId, string senderNodeId, string receiverNodeId);
    
    // 修饰符
    modifier onlyRegisteredNode(string memory nodeId) {
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");
        _;
    }
    
    modifier onlyActiveNode(string memory nodeId) {
        require(nodes[nodeId].isActive, "Node is not active");
        _;
    }
    
    /**
     * @dev 注册新节点
     */
    function registerNode(
        string memory nodeId,
        string memory name,
        string memory ipAddress,
        uint256 port
    ) external {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        require(bytes(nodes[nodeId].nodeId).length == 0, "Node already registered");

        nodes[nodeId] = NodeInfo({
            nodeId: nodeId,
            name: name,
            ipAddress: ipAddress,
            port: port,
            kyberPublicKey: "",
            falconPublicKey: "",
            kyberPublicKeyHash: "",  // 初始化Kyber哈希
            falconPublicKeyHash: "",  // 初始化Falcon哈希
            isActive: true,
            registrationTime: block.timestamp,
            lastUpdateTime: block.timestamp
        });

        addressToNodeId[msg.sender] = nodeId;
        nodeList.push(nodeId);

        emit NodeRegistered(nodeId, name, msg.sender);
    }
    
    /**
     * @dev 上传Kyber公钥
     */
    function uploadKyberPublicKey(
        string memory nodeId,
        bytes memory kyberPublicKey
    ) external onlyRegisteredNode(nodeId) onlyActiveNode(nodeId) {
        require(kyberPublicKey.length > 0, "Kyber public key cannot be empty");
        
        nodes[nodeId].kyberPublicKey = kyberPublicKey;
        nodes[nodeId].lastUpdateTime = block.timestamp;
        
        emit KyberKeyUploaded(nodeId, kyberPublicKey);
    }
    
    /**
     * @dev 上传Falcon公钥
     */
    function uploadFalconPublicKey(
        string memory nodeId,
        bytes memory falconPublicKey
    ) external onlyRegisteredNode(nodeId) onlyActiveNode(nodeId) {
        require(falconPublicKey.length > 0, "Falcon public key cannot be empty");
        require(nodes[nodeId].kyberPublicKey.length > 0, "Kyber public key must be uploaded first");
        
        nodes[nodeId].falconPublicKey = falconPublicKey;
        nodes[nodeId].lastUpdateTime = block.timestamp;
        
        emit FalconKeyUploaded(nodeId, falconPublicKey);
    }

    /**
     * @dev 上传Falcon公钥哈希值（用于大型V2密钥）
     */
    function uploadFalconPublicKeyHash(
        string memory nodeId,
        string memory publicKeyHash
    ) external onlyRegisteredNode(nodeId) onlyActiveNode(nodeId) {
        require(bytes(publicKeyHash).length > 0, "Public key hash cannot be empty");
        require(nodes[nodeId].kyberPublicKey.length > 0, "Kyber public key must be uploaded first");

        nodes[nodeId].falconPublicKeyHash = publicKeyHash;
        nodes[nodeId].lastUpdateTime = block.timestamp;

        emit FalconKeyHashUploaded(nodeId, publicKeyHash);
    }

    /**
     * @dev 记录会话密钥交换
     */
    function recordSessionKeyExchange(
        string memory sessionId,
        string memory fromNodeId,
        string memory toNodeId,
        bytes memory encryptedSessionKey,
        bytes memory signature
    ) external onlyRegisteredNode(fromNodeId) onlyActiveNode(fromNodeId) {
        require(bytes(sessionId).length > 0, "Session ID cannot be empty");
        require(bytes(nodes[toNodeId].nodeId).length > 0, "Target node not registered");
        require(nodes[toNodeId].isActive, "Target node is not active");
        require(encryptedSessionKey.length > 0, "Encrypted session key cannot be empty");
        require(signature.length > 0, "Signature cannot be empty");
        
        keyExchanges[sessionId] = KeyExchangeRecord({
            sessionId: sessionId,
            fromNodeId: fromNodeId,
            toNodeId: toNodeId,
            encryptedSessionKey: encryptedSessionKey,
            signature: signature,
            timestamp: block.timestamp,
            isValid: true
        });
        
        emit SessionKeyExchanged(sessionId, fromNodeId, toNodeId);
    }
    
    /**
     * @dev 获取节点信息
     */
    function getNodeInfo(string memory nodeId) external view returns (
        string memory name,
        string memory ipAddress,
        uint256 port,
        bytes memory kyberPublicKey,
        bytes memory falconPublicKey,
        bool isActive,
        uint256 registrationTime,
        uint256 lastUpdateTime
    ) {
        NodeInfo memory node = nodes[nodeId];
        return (
            node.name,
            node.ipAddress,
            node.port,
            node.kyberPublicKey,
            node.falconPublicKey,
            node.isActive,
            node.registrationTime,
            node.lastUpdateTime
        );
    }
    
    /**
     * @dev 获取节点的Kyber公钥
     */
    function getKyberPublicKey(string memory nodeId) external view returns (bytes memory) {
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");
        return nodes[nodeId].kyberPublicKey;
    }
    
    /**
     * @dev 获取节点的Falcon公钥
     */
    function getFalconPublicKey(string memory nodeId) external view returns (bytes memory) {
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");
        return nodes[nodeId].falconPublicKey;
    }

    /**
     * @dev 获取节点的Falcon公钥哈希值
     */
    function getFalconPublicKeyHash(string memory nodeId) external view returns (string memory) {
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");
        return nodes[nodeId].falconPublicKeyHash;
    }

    /**
     * @dev 获取会话密钥交换记录
     */
    function getSessionKeyExchange(string memory sessionId) external view returns (
        string memory fromNodeId,
        string memory toNodeId,
        bytes memory encryptedSessionKey,
        bytes memory signature,
        uint256 timestamp,
        bool isValid
    ) {
        KeyExchangeRecord memory record = keyExchanges[sessionId];
        return (
            record.fromNodeId,
            record.toNodeId,
            record.encryptedSessionKey,
            record.signature,
            record.timestamp,
            record.isValid
        );
    }
    
    /**
     * @dev 获取所有节点列表
     */
    function getAllNodes() external view returns (string[] memory) {
        return nodeList;
    }

    /**
     * @dev 修复nodeList - 添加缺失的节点ID到nodeList
     * 用于处理节点已在nodes映射中但未在nodeList中的情况
     */
    function syncNodeList(string memory nodeId) external {
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");

        // 检查节点ID是否已在nodeList中
        bool exists = false;
        for (uint i = 0; i < nodeList.length; i++) {
            if (keccak256(abi.encodePacked(nodeList[i])) == keccak256(abi.encodePacked(nodeId))) {
                exists = true;
                break;
            }
        }

        // 如果不存在，添加到nodeList
        if (!exists) {
            nodeList.push(nodeId);
        }
    }

    /**
     * @dev 获取节点数量
     */
    function getNodeCount() external view returns (uint256) {
        return nodeList.length;
    }
    
    /**
     * @dev 设置节点状态
     */
    function setNodeStatus(string memory nodeId, bool isActive) external onlyRegisteredNode(nodeId) {
        nodes[nodeId].isActive = isActive;
        nodes[nodeId].lastUpdateTime = block.timestamp;
        
        emit NodeStatusChanged(nodeId, isActive);
    }
    
    /**
     * @dev 检查节点是否存在
     */
    function nodeExists(string memory nodeId) external view returns (bool) {
        return bytes(nodes[nodeId].nodeId).length > 0;
    }
    
    /**
     * @dev 检查节点是否有完整的密钥对
     */
    function hasCompleteKeys(string memory nodeId) external view returns (bool) {
        return nodes[nodeId].kyberPublicKey.length > 0 && nodes[nodeId].falconPublicKey.length > 0;
    }

    /**
     * @dev 存储Kyber公钥哈希值
     */
    function storeKyberHash(string memory nodeId, string memory publicKeyHash) external {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        require(bytes(publicKeyHash).length > 0, "Hash cannot be empty");
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");

        nodes[nodeId].kyberPublicKeyHash = publicKeyHash;
        nodes[nodeId].lastUpdateTime = block.timestamp;

        emit KyberKeyHashUploaded(nodeId, publicKeyHash);
    }

    /**
     * @dev 获取Kyber公钥哈希值
     */
    function getKyberHash(string memory nodeId) external view returns (string memory) {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");

        return nodes[nodeId].kyberPublicKeyHash;
    }

    /**
     * @dev 存储Falcon公钥哈希值
     */
    function storeFalconHash(string memory nodeId, string memory publicKeyHash) external {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        require(bytes(publicKeyHash).length > 0, "Hash cannot be empty");
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");

        nodes[nodeId].falconPublicKeyHash = publicKeyHash;
        nodes[nodeId].lastUpdateTime = block.timestamp;

        emit FalconKeyHashUploaded(nodeId, publicKeyHash);
    }

    /**
     * @dev 获取Falcon公钥哈希值
     */
    function getFalconHash(string memory nodeId) external view returns (string memory) {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        require(bytes(nodes[nodeId].nodeId).length > 0, "Node not registered");

        return nodes[nodeId].falconPublicKeyHash;
    }

    /**
     * @dev 检查节点是否有Falcon公钥哈希
     */
    function hasFalconHash(string memory nodeId) external view returns (bool) {
        return bytes(nodes[nodeId].falconPublicKeyHash).length > 0;
    }

    /**
     * @dev 记录加密消息到区块链
     */
    function recordMessage(
        string memory messageId,
        string memory sessionId,
        string memory senderNodeId,
        string memory receiverNodeId,
        string memory ciphertextHash,
        string memory algorithm
    ) external {
        require(bytes(messageId).length > 0, "Message ID cannot be empty");
        require(bytes(sessionId).length > 0, "Session ID cannot be empty");
        require(bytes(senderNodeId).length > 0, "Sender node ID cannot be empty");
        require(bytes(receiverNodeId).length > 0, "Receiver node ID cannot be empty");
        require(bytes(ciphertextHash).length > 0, "Ciphertext hash cannot be empty");

        messageRecords[messageId] = MessageRecord({
            messageId: messageId,
            sessionId: sessionId,
            senderNodeId: senderNodeId,
            receiverNodeId: receiverNodeId,
            ciphertextHash: ciphertextHash,
            algorithm: algorithm,
            timestamp: block.timestamp
        });

        messageList.push(messageId);

        emit MessageRecorded(messageId, sessionId, senderNodeId, receiverNodeId);
    }

    /**
     * @dev 获取消息记录
     */
    function getMessageRecord(string memory messageId) external view returns (
        string memory sessionId,
        string memory senderNodeId,
        string memory receiverNodeId,
        string memory ciphertextHash,
        string memory algorithm,
        uint256 timestamp
    ) {
        MessageRecord memory record = messageRecords[messageId];
        return (
            record.sessionId,
            record.senderNodeId,
            record.receiverNodeId,
            record.ciphertextHash,
            record.algorithm,
            record.timestamp
        );
    }

    /**
     * @dev 获取消息总数
     */
    function getMessageCount() external view returns (uint256) {
        return messageList.length;
    }
}
