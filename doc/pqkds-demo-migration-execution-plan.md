# PQKDS 分发 Demo 融合执行规划

> 本文档用于指导后续多个 agent 分阶段把 `kms-distribute/extracted/ruoyi (2)` 中的 PQKDS/Falcon-KDS demo 融入当前 KMS 项目。
>
> 核心原则：**概念迁移，不做代码平移；领域重建，不引入双技术栈；FISCO 统一，不保留 Ganache；用户前台简化，管理员后台保留运维能力；安全实现重写，不复用 demo 的敏感材料处理方式。**

## 0. 前置准备：恢复外部 demo 源码

后续 agent 开始任何迁移、调研或实现前，必须先确认外部 demo 已解压。

源压缩包：

```text
kms-distribute/111.7z
```

期望解压目录：

```text
kms-distribute/extracted/ruoyi (2)
```

如果 `kms-distribute/extracted/ruoyi (2)` 不存在，先执行解压：

```bash
7z x "kms-distribute/111.7z" -o"kms-distribute/extracted"
```

解压后至少应能看到：

```text
kms-distribute/extracted/ruoyi (2)/backend/pqkds
kms-distribute/extracted/ruoyi (2)/web/src/views/pqkds
kms-distribute/extracted/ruoyi (2)/API_接口.md
kms-distribute/extracted/ruoyi (2)/QUICK_START.md
```

说明：本文档中的 demo 路径均基于上述解压目录。如果用户删除了解压目录，不要改文档路径，也不要跳过 demo 对照；应先从 `111.7z` 重新解压再继续。

## 1. 当前结论

外部 demo 是一个独立的 Django/Python + Vue + Ganache/Web3.py 后量子密钥分发原型。它的价值在于：

1. 节点注册与节点公钥管理流程。
2. 节点到节点的会话密钥建立流程。
3. Kyber/Falcon 风格的公钥体系用于分发 AES 对称会话密钥。
4. 单向预分发密钥池 `sender -> receiver`。
5. 会话消息、消息摘要和链上证据的演示。
6. 节点密钥更新后触发会话失效的业务思路。

它不能整体并入当前系统，原因是：

1. 技术栈不同：demo 是 Django/DRF/DVAdmin/Python/Web3.py/Ganache；当前主系统是 RuoYi/Spring Boot/Java/Go/Vue/Kafka/FISCO。
2. 权限体系不同：demo PQKDS 页面基本是 admin 运维视角；当前项目已有 `sys_user/sys_role/sys_menu/role_level/permission_request`。
3. 链体系不同：demo 使用 Ganache + Solidity 0.8；当前项目使用 FISCO BCOS + Java SDK + Solidity 0.4.x 风格合约。
4. 数据模型不同：demo 是 Node/SessionKey/Message/PreDistributedKey/BlockchainConfig；当前项目是 sys_user + keymanage + key_distribute_record + key_operation_record。
5. 安全边界不满足生产要求：demo 中存在私钥/部分私钥落库、本地 JSON 明文密钥池、Falcon 加密语义混用等问题。

因此迁移目标不是“搬代码”，而是把 demo 抽象成新的 `kms-distribute` 业务域。

## 2. 目标架构

目标架构如下：

```text
Gateway / Nginx
  ├── /user
  ├── /generate-api
  ├── /lifecycle-api
  ├── /distribute-api
  └── 内部 chain-adapter / key_chain_task

Identity / Admin 基座
  ├── sys_user
  ├── sys_role
  ├── sys_menu
  ├── sys_user_role
  ├── permission_request
  └── audit/log

kms-generate domain
  ├── SM2
  ├── SSCL
  ├── CL-Kyber / ML-KEM 方向
  ├── CL-Falcon / Falcon 签名方向
  ├── keymanage
  └── key_generate_log / ENROLL / key_chain_task

kms-lifecycle domain
  ├── UPDATE
  ├── REVOKE
  ├── auto-update
  ├── key_operation_record
  ├── session invalidation trigger
  └── key_update_log / key_revoke_log / key_chain_task

kms-distribute domain
  ├── kms_node
  ├── kms_node_binding
  ├── kms_node_key_material
  ├── kms_session_key
  ├── kms_secure_message
  ├── kms_pre_distributed_key
  ├── kms_blockchain_config
  ├── kms_session_invalidation
  ├── kms_distribution_evidence
  └── key_chain_task / key_chain_result integration

FISCO evidence layer
  ├── KeyEvidence            现有密钥生命周期存证
  ├── NodeRegistry           新增节点证据
  ├── SessionEvidence        新增会话证据
  └── MessageEvidence        新增消息摘要证据
```

## 3. 领域边界

### 3.1 `kms-generate` 负责

1. 生成系统中的密钥资产。
2. 新增 `CL-Kyber`、`CL-Falcon` 或等价算法选项。
3. 保存 `keymanage` 记录。
4. 生成侧上链任务。
5. 向分发域提供可绑定的通信密钥资产。

不负责：

1. 节点绑定。
2. 会话密钥协商。
3. 消息发送。
4. 预分发密钥池消费。

### 3.2 `kms-updatedel` 负责

1. 密钥更新、撤销、自动更新。
2. 权限申请、审批、回退。
3. key operation 审计。
4. 更新/撤销成功后通知分发域失效相关会话。

不负责：

1. 节点注册。
2. 预分发密钥池生成。
3. 消息通信。

### 3.3 `kms-distribute` 负责

1. 节点实体。
2. 用户-节点绑定。
3. 节点通信公钥绑定。
4. 预分发密钥池。
5. 会话密钥建立。
6. 安全消息收发。
7. 分发审计与链上证据。
8. 分发管理员后台能力。

### 3.4 `kms-user` 负责

1. 普通用户统一入口。
2. “节点通信/安全通信”前台页面。
3. 我的节点、发起通信、会话与消息、密钥池状态、权限申请。
4. 只展示用户有权限的数据。

不负责：

1. 节点注册/删除。
2. 密钥池批量生成/清理。
3. 区块链配置。
4. 全局审计。
5. 查看私钥、部分私钥、完整 session key。

## 4. 核心设计决策

### 4.1 字段可以拆分

不要把 Kyber/Falcon 公钥、密文、会话交换包、格参数、签名等大 JSON 直接塞入 `keymanage.key_value`。

原因：当前 SQL 中 `keymanage.key_value` 存在 `VARCHAR(1024)` 风险，无法可靠承载 Kyber/Falcon 大字段。

处理方式：

1. `keymanage` 只保存密钥资产主记录和摘要。
2. 节点通信公钥、密钥版本、密钥引用放入 `kms_node_key_material`。
3. 会话交换数据放入 `kms_session_key`。
4. 消息密文和摘要放入 `kms_secure_message`。
5. 预分发密钥包放入 `kms_pre_distributed_key`。

### 4.2 用户和节点必须绑定

新增 `kms_node_binding`，不要把 `Node` 直接等同 `sys_user`。

用户是身份、权限、审计主体；节点是通信、公钥、会话密钥协商主体。

关系：

```text
sys_user.user_id 1 -> N kms_node_binding N -> 1 kms_node.node_id
```

### 4.3 前端必须规划给 Gemini 实现

后续前端实现建议交给 Gemini 或 designer agent，任务不能是“照搬 demo 页面”，而是按用户前台和管理员后台拆分。

`kms-user` 新增“节点通信/安全通信”用户前台；`kms-distribute/front` 或分发管理员后台保留 PQKDS 运维能力。

### 4.4 区块链迁移由本项目重新定合约

不要直接迁移 `FalconKDS.sol`。

保留现有 `KeyEvidence`，新增 FISCO 合约：

1. `NodeRegistry.sol`
2. `SessionEvidence.sol`
3. `MessageEvidence.sol`

如果实现成本需要降低，也可以先合并为一个 `DistributionEvidence.sol`，但不要把全部分发字段硬塞进 `KeyEvidence`。

### 4.5 权限参考当前项目

权限沿用当前项目已有思路：

1. `sys_user`
2. `sys_role`
3. `sys_menu`
4. `role_level`
5. `permission_request`
6. `@PreAuthorize` / 菜单权限

新增分发能力申请项，而不是使用 demo 的 admin-only 路由。

## 5. 数据表设计

### 5.1 `kms_node`

用途：通信节点主表。

```sql
CREATE TABLE kms_node (
  id BIGINT NOT NULL AUTO_INCREMENT,
  node_id VARCHAR(128) NOT NULL,
  node_name VARCHAR(100) NOT NULL,
  node_type VARCHAR(32) DEFAULT 'USER_NODE',
  ip_address VARCHAR(64),
  port INT,
  organization VARCHAR(128),
  department VARCHAR(128),
  location VARCHAR(255),
  contact VARCHAR(100),
  email VARCHAR(128),
  phone VARCHAR(64),
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  blockchain_config_id BIGINT,
  last_active_time DATETIME,
  create_time DATETIME,
  update_time DATETIME,
  remark VARCHAR(500),
  PRIMARY KEY (id),
  UNIQUE KEY uk_kms_node_node_id (node_id),
  KEY idx_kms_node_status (status)
);
```

建议状态：

```text
PENDING
ACTIVE
FROZEN
OFFLINE
REVOKED
DELETED
```

### 5.2 `kms_node_binding`

用途：用户和节点绑定关系。

```sql
CREATE TABLE kms_node_binding (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  user_name VARCHAR(100),
  node_id VARCHAR(128) NOT NULL,
  bind_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  default_flag TINYINT DEFAULT 0,
  approved_by BIGINT,
  approved_time DATETIME,
  expire_time DATETIME,
  create_time DATETIME,
  update_time DATETIME,
  remark VARCHAR(500),
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_node (user_id, node_id),
  KEY idx_node_binding_node (node_id),
  KEY idx_node_binding_status (bind_status)
);
```

绑定状态：

```text
PENDING
BOUND
REJECTED
UNBOUND
EXPIRED
```

### 5.3 `kms_node_key_material`

用途：节点通信公钥、密钥版本、密钥引用。不要明文保存私钥。

```sql
CREATE TABLE kms_node_key_material (
  id BIGINT NOT NULL AUTO_INCREMENT,
  node_id VARCHAR(128) NOT NULL,
  key_id BIGINT,
  algorithm VARCHAR(64) NOT NULL,
  security_level VARCHAR(32),
  public_key MEDIUMTEXT,
  public_key_hash VARCHAR(128),
  private_key_ref VARCHAR(255),
  partial_key_ref VARCHAR(255),
  lattice_params MEDIUMTEXT,
  key_version INT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  KEY idx_node_key_node (node_id),
  KEY idx_node_key_key_id (key_id),
  KEY idx_node_key_hash (public_key_hash),
  KEY idx_node_key_algo_status (algorithm, status)
);
```

字段说明：

1. `key_id` 可关联 `keymanage.key_id`。
2. `public_key` 可保存通信公钥大字段。
3. `private_key_ref` 是私钥引用，不是明文私钥。
4. `partial_key_ref` 是部分私钥引用，不是明文部分私钥。
5. `lattice_params` 存非敏感参数或参数摘要；敏感格秘密不落库。

### 5.4 `kms_session_key`

用途：节点间会话密钥建立记录。

```sql
CREATE TABLE kms_session_key (
  id BIGINT NOT NULL AUTO_INCREMENT,
  session_id VARCHAR(128) NOT NULL,
  sender_user_id BIGINT,
  receiver_user_id BIGINT,
  sender_node_id VARCHAR(128) NOT NULL,
  receiver_node_id VARCHAR(128) NOT NULL,
  session_type VARCHAR(64) NOT NULL,
  algorithm VARCHAR(64) NOT NULL,
  encrypted_session_key MEDIUMTEXT,
  key_exchange_data MEDIUMTEXT,
  kem_ciphertext_hash VARCHAR(128),
  signature_hash VARCHAR(128),
  nonce VARCHAR(128),
  tag VARCHAR(128),
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  used_pre_key_id BIGINT,
  expires_at DATETIME,
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  UNIQUE KEY uk_session_id (session_id),
  KEY idx_session_sender_node (sender_node_id),
  KEY idx_session_receiver_node (receiver_node_id),
  KEY idx_session_users (sender_user_id, receiver_user_id),
  KEY idx_session_status (status)
);
```

会话状态：

```text
PENDING
ACTIVE
EXPIRED
CLOSED
INVALIDATED
FAILED
```

### 5.5 `kms_secure_message`

用途：会话内安全消息。默认不保存明文。

```sql
CREATE TABLE kms_secure_message (
  id BIGINT NOT NULL AUTO_INCREMENT,
  message_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128) NOT NULL,
  sender_user_id BIGINT,
  receiver_user_id BIGINT,
  sender_node_id VARCHAR(128) NOT NULL,
  receiver_node_id VARCHAR(128) NOT NULL,
  encrypted_content MEDIUMTEXT NOT NULL,
  ciphertext_hash VARCHAR(128),
  message_digest VARCHAR(128),
  message_type VARCHAR(32) DEFAULT 'TEXT',
  delivered TINYINT DEFAULT 0,
  read_flag TINYINT DEFAULT 0,
  sent_at DATETIME,
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  UNIQUE KEY uk_message_id (message_id),
  KEY idx_message_session (session_id),
  KEY idx_message_sender (sender_user_id, sender_node_id),
  KEY idx_message_receiver (receiver_user_id, receiver_node_id),
  KEY idx_message_digest (message_digest)
);
```

### 5.6 `kms_pre_distributed_key`

用途：单向预分发密钥池。

```sql
CREATE TABLE kms_pre_distributed_key (
  id BIGINT NOT NULL AUTO_INCREMENT,
  pool_id VARCHAR(128) NOT NULL,
  key_index INT NOT NULL,
  sender_user_id BIGINT,
  receiver_user_id BIGINT,
  sender_node_id VARCHAR(128) NOT NULL,
  receiver_node_id VARCHAR(128) NOT NULL,
  algorithm VARCHAR(64) NOT NULL,
  encrypted_key_data MEDIUMTEXT NOT NULL,
  key_hash VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'UNUSED',
  used_at DATETIME,
  used_by_session_id VARCHAR(128),
  expires_at DATETIME,
  generation_time_ms DOUBLE,
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  UNIQUE KEY uk_pool_key (pool_id, key_index),
  KEY idx_pre_key_pair (sender_node_id, receiver_node_id),
  KEY idx_pre_key_status (status),
  KEY idx_pre_key_hash (key_hash)
);
```

状态：

```text
UNUSED
USED
EXPIRED
REVOKED
```

### 5.7 `kms_blockchain_config`

用途：FISCO 合约配置版本。不要保存明文私钥。

```sql
CREATE TABLE kms_blockchain_config (
  id BIGINT NOT NULL AUTO_INCREMENT,
  config_name VARCHAR(100) NOT NULL,
  chain_type VARCHAR(32) NOT NULL DEFAULT 'FISCO',
  provider_url VARCHAR(512),
  group_id INT,
  contract_name VARCHAR(100),
  contract_address VARCHAR(128),
  contract_abi MEDIUMTEXT,
  account_address VARCHAR(128),
  private_key_ref VARCHAR(255),
  gas_limit BIGINT,
  gas_price BIGINT,
  is_active TINYINT DEFAULT 0,
  config_version INT NOT NULL DEFAULT 1,
  status VARCHAR(32) DEFAULT 'ACTIVE',
  create_time DATETIME,
  update_time DATETIME,
  remark VARCHAR(500),
  PRIMARY KEY (id),
  KEY idx_chain_config_active (is_active, status),
  KEY idx_chain_config_contract (contract_name, contract_address)
);
```

合约地址变化时：

1. 不物理删除旧交易。
2. 不解绑历史节点。
3. 旧配置标记 `INACTIVE`。
4. 新配置递增 `config_version`。

### 5.8 `kms_session_invalidation`

用途：节点密钥更新/撤销后失效相关会话。

```sql
CREATE TABLE kms_session_invalidation (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invalidation_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128) NOT NULL,
  node_id VARCHAR(128) NOT NULL,
  key_id BIGINT,
  old_key_version INT,
  new_key_version INT,
  reason VARCHAR(255),
  status VARCHAR(32) DEFAULT 'PENDING',
  operation_record_id BIGINT,
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  UNIQUE KEY uk_invalidation_id (invalidation_id),
  KEY idx_invalidation_session (session_id),
  KEY idx_invalidation_node (node_id)
);
```

### 5.9 `chain_outbox`

用途：统一上链补偿、幂等和重试。

```sql
CREATE TABLE chain_outbox (
  id BIGINT NOT NULL AUTO_INCREMENT,
  evidence_type VARCHAR(64) NOT NULL,
  business_id VARCHAR(128) NOT NULL,
  action_type VARCHAR(64) NOT NULL,
  payload MEDIUMTEXT NOT NULL,
  idempotency_key VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  retry_count INT DEFAULT 0,
  next_retry_time DATETIME,
  last_error TEXT,
  chain_hash VARCHAR(128),
  block_height BIGINT,
  create_time DATETIME,
  update_time DATETIME,
  PRIMARY KEY (id),
  UNIQUE KEY uk_chain_idempotency (idempotency_key),
  KEY idx_chain_outbox_status (status, next_retry_time),
  KEY idx_chain_outbox_business (evidence_type, business_id)
);
```

## 6. 现有表增强

### 6.1 `keymanage`

建议：

1. `key_id` 从 `INT` 升级为 `BIGINT`。
2. `key_value` 从 `VARCHAR(1024)` 升级为 `MEDIUMTEXT`，或只保存摘要/兼容旧算法 JSON。
3. 新增或确认存在：
   - `public_key_hash VARCHAR(128)`
   - `key_material_ref VARCHAR(255)`
   - `algorithm_version VARCHAR(64)`
4. `cre_time/upd_time` 后续逐步迁移为 `DATETIME`。

### 6.2 `key_distribute_record`

建议增加：

```text
pool_id
pre_key_id
sender_node_id
receiver_node_id
session_id
message_id
evidence_type
```

用途：让旧分发记录可以和新 PQKDS 分发事件关联。

### 6.3 `key_operation_record`

建议增加：

```text
node_id
session_invalidation_count
related_session_ids
```

用途：密钥更新/撤销后可追踪影响了哪些节点会话。

### 6.4 `permission_request`

需要校准 Java domain 与 SQL。建议补齐：

```text
system_code
feature_code
feature_name
target_id
target_type
expire_time
```

用于承载：

```text
NODE_BIND
TARGET_NODE_ACCESS
SESSION_INITIATE
KEY_POOL_REPLENISH_REQUEST
AUDIT_EXPORT
NODE_FREEZE
```

## 7. API 设计

所有分发接口建议统一在：

```text
/distribute/pqkds/*
```

或更用户化：

```text
/distribute/communication/*
```

### 7.1 用户前台 API

#### 我的节点

```text
GET /distribute/communication/my-nodes
GET /distribute/communication/my-nodes/default
POST /distribute/communication/node-bind/apply
GET /distribute/communication/node-bind/requests
```

#### 目标用户与目标节点

```text
GET /distribute/communication/target-users
GET /distribute/communication/target-users/{userId}/nodes
POST /distribute/communication/target-access/apply
```

#### 会话

```text
GET /distribute/communication/sessions
GET /distribute/communication/sessions/{sessionId}
POST /distribute/communication/sessions
POST /distribute/communication/sessions/{sessionId}/close
GET /distribute/communication/sessions/{sessionId}/chain
```

创建会话请求：

```json
{
  "senderNodeId": "node-a",
  "receiverUserId": 1002,
  "receiverNodeId": "node-b",
  "keySource": "AUTO",
  "algorithm": "CL-KYBER",
  "expireMinutes": 60
}
```

`keySource`：

```text
AUTO              优先预分发池，不足则实时协商或提示申请补池
PREDISTRIBUTED    强制使用预分发池
REALTIME          实时协商
```

#### 消息

```text
GET /distribute/communication/sessions/{sessionId}/messages
POST /distribute/communication/sessions/{sessionId}/messages
POST /distribute/communication/messages/{messageId}/read
GET /distribute/communication/messages/{messageId}/chain
```

发送消息请求：

```json
{
  "content": "前端可传明文给服务端演示，也可后续改端侧加密",
  "messageType": "TEXT"
}
```

安全目标：后端落库只保存密文和摘要，不保存明文。

#### 密钥池只读状态

```text
GET /distribute/communication/key-pool/status
GET /distribute/communication/key-pool/status?targetUserId=1002&targetNodeId=node-b
POST /distribute/communication/key-pool/replenish-apply
```

普通用户只能查看余量和申请补池，不能直接生成、清理、删除密钥池。

### 7.2 管理员后台 API

#### 节点管理

```text
GET /distribute/admin/nodes
GET /distribute/admin/nodes/{nodeId}
POST /distribute/admin/nodes
PUT /distribute/admin/nodes/{nodeId}
DELETE /distribute/admin/nodes/{nodeId}
POST /distribute/admin/nodes/{nodeId}/freeze
POST /distribute/admin/nodes/{nodeId}/unfreeze
POST /distribute/admin/nodes/{nodeId}/bind-user
POST /distribute/admin/nodes/{nodeId}/unbind-user
```

#### 节点密钥

```text
GET /distribute/admin/nodes/{nodeId}/keys
POST /distribute/admin/nodes/{nodeId}/keys/bind-keymanage
POST /distribute/admin/nodes/{nodeId}/keys/update-version
POST /distribute/admin/nodes/{nodeId}/keys/upload-public-hash
```

#### 密钥池运维

```text
GET /distribute/admin/key-pools
POST /distribute/admin/key-pools/generate
POST /distribute/admin/key-pools/replenish
POST /distribute/admin/key-pools/cleanup-expired
DELETE /distribute/admin/key-pools/{poolId}
POST /distribute/admin/key-pools/batch-delete
```

#### 全局会话与消息审计

```text
GET /distribute/admin/sessions
GET /distribute/admin/sessions/{sessionId}
POST /distribute/admin/sessions/{sessionId}/invalidate
GET /distribute/admin/messages
GET /distribute/admin/evidence
```

#### 链配置

```text
GET /distribute/admin/blockchain-configs
POST /distribute/admin/blockchain-configs
PUT /distribute/admin/blockchain-configs/{id}
POST /distribute/admin/blockchain-configs/{id}/activate
GET /distribute/admin/blockchain-configs/{id}/status
```

## 8. 前端规划

### 8.1 给 Gemini 的总体要求

后续可让 Gemini 负责前端实现。Gemini 任务必须明确：**不要照搬 demo admin 页面到 `kms-user`，而是拆成用户前台和管理员后台。**

### 8.2 `kms-user` 新增模块

模块名建议：

```text
节点通信
```

或：

```text
安全通信
```

路由建议：

```text
/communication
/communication/nodes
/communication/start
/communication/sessions
/communication/sessions/:sessionId
/communication/key-pool
/communication/permissions
```

页面设计：

1. **我的节点**
   - 显示当前用户绑定节点。
   - 显示节点状态、默认节点、可用算法、链上同步状态。
   - 提供“申请绑定节点”。
   - 不提供注册节点、删除节点、更新节点密钥。

2. **发起通信**
   - 第一步：选择我的发送节点。
   - 第二步：选择目标用户。
   - 第三步：选择目标用户可通信节点。
   - 第四步：选择密钥来源：自动/预分发池/实时协商。
   - 第五步：提交创建会话。
   - 如果密钥池不足，提示“申请补池”。

3. **会话与消息**
   - 展示我的会话。
   - 支持进入对话。
   - 展示算法、状态、创建时间、过期时间、链上交易哈希。
   - 不展示完整 session key、私钥、部分私钥、完整签名。
   - 密文可隐藏，最多展示摘要。

4. **密钥池状态**
   - 按方向展示：我方节点 -> 目标节点。
   - 展示可用余量、过期风险、最近补充时间。
   - 提供“申请补充”。
   - 不提供生成、清理、删除、批删。

5. **权限申请**
   - 复用当前 `PermissionView.vue` 思路。
   - 新增 featureCode：
     - `NODE_BIND`
     - `TARGET_NODE_ACCESS`
     - `SESSION_INITIATE`
     - `KEY_POOL_REPLENISH_REQUEST`
     - `AUDIT_EXPORT`

### 8.3 `kms-distribute` 管理员后台

保留/新增 PQKDS 运维能力：

```text
/pqkds/dashboard
/pqkds/nodes
/pqkds/node-bindings
/pqkds/key-pool
/pqkds/sessions
/pqkds/messages-audit
/pqkds/blockchain
/pqkds/logs
```

管理员页面可以参考 demo：

1. `web/src/views/pqkds/nodes/index.vue`
2. `web/src/views/pqkds/keyPool/index.vue`
3. `web/src/views/pqkds/sessions/index.vue`
4. `web/src/views/pqkds/blockchain/index.vue`

但必须改造：

1. 接入 RuoYi token。
2. 接入 `/distribute-api`。
3. 去掉 Ganache 配置语言。
4. 使用 FISCO/合约证据术语。
5. 隐藏或脱敏敏感密钥字段。

### 8.4 Gemini 实施任务包

#### Gemini 任务 1：`kms-user` 节点通信前台壳

输入：

```text
实现 kms-user/front 中的节点通信模块，只做前端壳和 API 调用封装，不写后端。
参考 doc/frontend-role-boundary.md：kms-user 只承接普通用户能力，不承接管理员运维。
新增路由、菜单、页面：我的节点、发起通信、会话与消息、密钥池状态、权限申请入口。
不要迁入 demo 的 admin 节点管理/区块链管理/密钥池批量操作。
```

验收：

1. 普通用户页面没有注册节点/删除节点/清理密钥池按钮。
2. 会话详情不展示 session key。
3. 密钥池页面只读。
4. API 单独放 `communication-api.js`，不要污染旧 `distribute-api.js`。

#### Gemini 任务 2：会话与消息交互

输入：

```text
基于 demo sessions 页面交互思想，重做用户化会话与消息页面。
用户选择：我的节点 -> 目标用户 -> 目标节点 -> 密钥来源 -> 创建会话。
对话页展示消息列表、发送框、链上摘要、会话状态。
隐藏密钥明文、签名全文、密文大字段。
```

验收：

1. 会话创建流程清晰。
2. 目标选择先用户后节点。
3. 单向密钥池方向有明显提示。
4. 密钥池不足有补池申请入口。

#### Gemini 任务 3：管理员 PQKDS 运维页改造

输入：

```text
把 demo 的 nodes/keyPool/sessions/blockchain/logs 页面改造成 kms-distribute 管理后台页面。
保留管理员运维能力，但接入 RuoYi 权限和新 Java API。
不要使用 Ganache/Web3 文案。
```

验收：

1. 管理员可以管理节点、绑定、密钥池、会话审计、链配置。
2. 页面术语是 FISCO/节点证据/会话证据。
3. 删除操作有确认和审计提示。
4. 不展示明文私钥/部分私钥。

## 9. 权限设计

### 9.1 角色

沿用 `doc/frontend-role-boundary.md`：

1. 普通用户。
2. 临时授权用户。
3. 生成系统管理员。
4. 生命周期系统管理员。
5. 分发系统管理员。

新增分发域角色能力：

```text
普通用户：查看我的节点、申请绑定、发起授权会话、收发消息、查看自己的密钥池余量。
临时授权用户：可访问更多目标节点或申请补池，但不直接执行补池。
分发管理员：节点注册、节点绑定审批、目标访问审批、密钥池批量生成/清理、全局审计、链配置。
系统服务账号：执行真实密钥池下发、链上写入、会话失效任务。
```

### 9.2 权限申请 featureCode

新增：

```text
NODE_BIND
TARGET_NODE_ACCESS
SESSION_INITIATE
KEY_POOL_REPLENISH_REQUEST
AUDIT_EXPORT
NODE_FREEZE
```

建议字段：

```text
system_code = DISTRIBUTE
feature_code = NODE_BIND / TARGET_NODE_ACCESS / ...
feature_name = 节点绑定 / 目标节点访问 / ...
target_type = NODE / USER / SESSION / POOL
target_id = 目标对象 ID
```

### 9.3 接口权限

用户接口：

```text
@PreAuthorize("hasAuthority('distribute:communication:view')")
@PreAuthorize("hasAuthority('distribute:communication:session:create')")
```

管理员接口：

```text
@PreAuthorize("hasAuthority('distribute:node:manage')")
@PreAuthorize("hasAuthority('distribute:keypool:manage')")
@PreAuthorize("hasAuthority('distribute:blockchain:config')")
@PreAuthorize("hasAuthority('distribute:audit:list')")
```

业务校验必须在 Service 层再次执行：

1. 当前用户只能使用已绑定节点。
2. 当前用户只能访问已授权目标节点。
3. 会话双方节点必须状态 `ACTIVE`。
4. 预分发密钥池必须方向匹配：`sender_node_id -> receiver_node_id`。
5. 普通用户不能调用管理员运维接口。

## 10. 区块链合约设计

### 10.1 保留现有 `KeyEvidence`

继续负责：

1. `uploadKey`
2. `rotateKey`
3. `changeKeyStatus`

不要把节点、会话、消息全塞进 `KeyEvidence`。

### 10.2 新增 `NodeRegistry.sol`

职责：节点注册与节点公钥哈希存证。

建议结构：

```solidity
struct NodeRecord {
    string nodeId;
    string ownerHash;
    string nodeNameHash;
    string endpointHash;
    string kyberPublicKeyHash;
    string falconPublicKeyHash;
    string status;
    uint256 registeredAt;
    uint256 updatedAt;
}
```

建议方法：

```solidity
function registerNode(string nodeId, string ownerHash, string nodeNameHash, string endpointHash) public;
function updateNodeKeyHash(string nodeId, string algorithm, string publicKeyHash, uint256 version) public;
function changeNodeStatus(string nodeId, string status) public;
function getNode(string nodeId) public view returns (...);
```

建议事件：

```solidity
event NodeRegistered(string nodeId, string ownerHash, uint256 timestamp);
event NodeKeyHashUpdated(string nodeId, string algorithm, string publicKeyHash, uint256 version, uint256 timestamp);
event NodeStatusChanged(string nodeId, string status, uint256 timestamp);
```

### 10.3 新增 `SessionEvidence.sol`

职责：会话建立、关闭、失效、会话摘要存证。

建议结构：

```solidity
struct SessionRecord {
    string sessionId;
    string senderNodeId;
    string receiverNodeId;
    string kemAlgorithm;
    string signAlgorithm;
    string encryptedSessionKeyHash;
    string signatureHash;
    string sessionDigest;
    string status;
    uint256 createdAt;
    uint256 expiresAt;
}
```

建议方法：

```solidity
function recordSessionExchange(string sessionId, string senderNodeId, string receiverNodeId, string kemAlgorithm, string signAlgorithm, string encryptedSessionKeyHash, string signatureHash, string sessionDigest, uint256 expiresAt) public;
function changeSessionStatus(string sessionId, string status) public;
function recordSessionSummary(string sessionId, string messagesRoot, uint256 messageCount, string sessionDigest) public;
```

建议事件：

```solidity
event SessionExchangeRecorded(string sessionId, string senderNodeId, string receiverNodeId, uint256 timestamp);
event SessionStatusChanged(string sessionId, string status, uint256 timestamp);
event SessionSummaryRecorded(string sessionId, string messagesRoot, uint256 messageCount, uint256 timestamp);
```

### 10.4 新增 `MessageEvidence.sol`

职责：消息摘要存证。

建议结构：

```solidity
struct MessageRecord {
    string messageId;
    string sessionId;
    string senderNodeId;
    string receiverNodeId;
    string ciphertextHash;
    string messageDigest;
    string algorithm;
    uint256 timestamp;
}
```

建议方法：

```solidity
function recordMessageDigest(string messageId, string sessionId, string senderNodeId, string receiverNodeId, string ciphertextHash, string messageDigest, string algorithm) public;
function getMessage(string messageId) public view returns (...);
```

建议事件：

```solidity
event MessageDigestRecorded(string messageId, string sessionId, string messageDigest, uint256 timestamp);
```

### 10.5 链上字段原则

链上只存：

1. ID。
2. Hash。
3. Digest。
4. 状态。
5. 时间。
6. 必要算法名。

链上不存：

1. 私钥。
2. 部分私钥。
3. 明文 AES key。
4. 完整密文正文。
5. 大公钥字段。
6. 明文 IP/端口，如果敏感则存 `endpointHash`。

## 11. Kafka 与事件设计

参考 `doc/message-protocol.md`，保留现有 topic：

```text
key_generate_log
key_update_log
key_revoke_log
key_chain_task
key_chain_result
```

### 11.1 新增 action_type

```text
NODE_REGISTER
NODE_KEY_HASH_UPDATE
NODE_STATUS_CHANGE
SESSION_EXCHANGE
SESSION_STATUS_CHANGE
SESSION_SUMMARY
MESSAGE_DIGEST
PREDISTRIBUTED_KEY_CREATE
PREDISTRIBUTED_KEY_CONSUME
PREDISTRIBUTED_KEY_REVOKE
```

### 11.2 `key_chain_task` 扩展 payload

保留旧字段，新增可选字段。

```json
{
  "action_type": "SESSION_EXCHANGE",
  "key_id": null,
  "evidence_type": "SESSION",
  "business_id": "session-20260509-001",
  "node_id": null,
  "session_id": "session-20260509-001",
  "message_id": null,
  "digest": "hash...",
  "payload": {},
  "correlation_id": "trace-...",
  "idempotency_key": "SESSION:session-20260509-001:1"
}
```

### 11.3 `key_chain_result` 扩展 payload

```json
{
  "key_id": null,
  "action_type": "SESSION_EXCHANGE",
  "chain_status": 1,
  "chain_hash": "0x...",
  "block_height": 123,
  "error_message": null,
  "evidence_id": "session-20260509-001",
  "evidence_type": "SESSION",
  "node_id": null,
  "session_id": "session-20260509-001",
  "message_id": null,
  "digest": "hash...",
  "contract_address": "0x...",
  "event_name": "SessionExchangeRecorded",
  "correlation_id": "trace-...",
  "idempotency_key": "SESSION:session-20260509-001:1"
}
```

现有消费者应忽略未知字段；新增分发链消费者处理新增 action_type。

## 12. 安全实现要求

### 12.1 不允许的实现

1. 不允许明文保存 `kyber_private_key`。
2. 不允许明文保存 `falcon_private_key`。
3. 不允许明文保存 KGC 部分私钥。
4. 不允许把 AES key 明文保存到 JSON 文件。
5. 不允许静默 fallback 到 demo crypto。
6. 不允许把完整会话密钥材料上链。
7. 不允许普通用户看到 session key、私钥、部分私钥。

### 12.2 Kyber / ML-KEM

建议：

1. 密钥封装使用标准 Kyber/ML-KEM 或明确标注研究型 CL-Kyber。
2. 不直接使用 `shared_secret[:32]`。
3. 使用 HKDF/SHA3/KMAC 派生 AEAD key。
4. AAD 绑定：
   - sender_node_id
   - receiver_node_id
   - pool_id
   - key_index
   - algorithm
   - key_version
   - expires_at
5. nonce/ct/tag/signatureHash 纳入 digest。

### 12.3 Falcon

建议：

1. 标准 Falcon 用于签名认证。
2. 不把标准 Falcon 描述为加密/KEM。
3. demo 中 CL-Falcon 加密只能作为研究型原型，需要单独说明。
4. 若必须实现 CL-Falcon 加密，需独立任务进行算法审查和测试向量设计。

### 12.4 密钥池

生产目标：

1. 中心侧保存 `encrypted_key_data` 与元数据。
2. 节点侧保存 sealed key handle。
3. 明文 AES key 只在内存中短暂出现。
4. 消费操作必须原子化。
5. 同一 `pool_id + key_index` 只能消费一次。
6. 过期密钥不可消费。
7. 消费、过期、撤销都写审计。

## 13. 实施阶段

### 阶段 0：契约冻结

产物：

1. 本文档确认。
2. 状态枚举字典。
3. API 契约。
4. Kafka schema。
5. 合约字段确认。
6. 前端页面边界确认。

验收：

1. 没有直接迁移 Django 的计划。
2. 用户前台和管理员后台边界明确。
3. KeyEvidence 不被污染。
4. 所有敏感字段有归属策略。

### 阶段 1：数据库与实体

任务：

1. 新增 SQL。
2. 新增 Java domain。
3. 新增 Mapper XML。
4. 补齐 permission_request 字段。
5. 增强 keymanage/key_distribute_record/key_operation_record。

验收：

1. SQL 能按初始化顺序执行。
2. 大字段使用 TEXT/MEDIUMTEXT。
3. 索引使用 hash 列而不是大文本列。
4. 不出现明文私钥字段。

### 阶段 2：后端基础 API

任务：

1. 节点 CRUD/查询。
2. 节点绑定申请/审批。
3. 我的节点 API。
4. 目标用户/目标节点 API。
5. 密钥池只读状态 API。
6. 管理员密钥池运维 API。

验收：

1. 普通用户只能看自己的绑定节点。
2. 管理员可以管理节点。
3. Service 层有二次权限校验。
4. API 前缀和 Nginx 规划一致。

### 阶段 3：FISCO 合约与 chain-adapter

任务：

1. 编写 `NodeRegistry.sol`。
2. 编写 `SessionEvidence.sol`。
3. 编写 `MessageEvidence.sol`。
4. 生成 Java wrapper。
5. 抽象 FISCO client/contract client。
6. 实现 chain_outbox。
7. 扩展 key_chain_task/key_chain_result。

验收：

1. 合约能部署到 FISCO。
2. receipt 事件校验通过。
3. 幂等 key 生效。
4. 上链失败可重试。
5. 业务表能回填 chain_hash/block_height。

### 阶段 4：会话与密钥池业务

任务：

1. 创建会话。
2. 优先消费预分发密钥。
3. 预分发不足时走实时协商或补池申请。
4. 会话过期/关闭/失效。
5. 消息发送与消息摘要。

验收：

1. `sender_node -> receiver_node` 方向正确。
2. 预分发密钥只消费一次。
3. 会话状态流转正确。
4. 消息只落密文和摘要。
5. 会话/消息证据可上链。

### 阶段 5：生成系统算法接入

任务：

1. 新增 `CL-Kyber` 选项。
2. 新增 `CL-Falcon` 或 Falcon 签名选项。
3. 前端生成页面支持选择。
4. `GenerateChainServiceImpl` 按 `encrytName` 分支处理。
5. keymanage 大字段策略落实。

验收：

1. 新算法生成记录可保存。
2. 公钥/摘要可被节点绑定。
3. 旧 SM2/SSCL 不受影响。
4. 上链逻辑不再通过是否存在 `SSCLKey` 隐式判断。

### 阶段 6：前端实现

任务：

1. Gemini 实现 `kms-user` 节点通信前台。
2. Gemini 实现会话与消息交互。
3. Gemini 改造管理员 PQKDS 页面。
4. 接入权限申请。
5. 接入链上证据展示。

验收：

1. 普通用户看不到管理员按钮。
2. 普通用户看不到 session key/私钥。
3. 目标选择是用户 -> 节点两级。
4. 密钥池方向清晰。
5. 补池走申请，不直接执行。

### 阶段 7：生命周期联动

任务：

1. 密钥更新后更新节点密钥版本。
2. 撤销后冻结/失效相关节点密钥。
3. 失效受影响会话。
4. 写 `kms_session_invalidation`。
5. 写链上会话状态变更。

验收：

1. 更新/撤销能影响相关会话。
2. 审计能从 key_operation_record 追踪到 session invalidation。
3. 用户前台能看到会话已失效。

### 阶段 8：ops 收敛

任务：

1. 更新 Nginx。
2. 更新 docker-compose。
3. 更新初始化 SQL。
4. 更新环境变量。
5. 移除 Ganache/Web3.py 运行依赖。
6. 删除或归档 extracted demo。

验收：

1. `/user` 正常。
2. `/distribute-api` 正常。
3. Kafka topic 正常。
4. FISCO 合约地址配置正常。
5. 不再依赖 Django demo 服务。

## 14. 后续 agent 任务拆分

### Agent A：数据库与实体实现

范围：

1. 新增 SQL。
2. Java domain。
3. Mapper XML。
4. 基础 Service。

输入文件：

1. 本文档。
2. `kms-ops/mysql/init/*.sql`
3. `kms-distribute/java-backend/**`
4. `kms-generate/java-backend/**/Keymanage.java`
5. `kms-updatedel/**/PermissionRequest*`

验收：

1. SQL 初始化成功。
2. 编译通过。
3. 无明文私钥字段。

### Agent B：权限与用户节点绑定

范围：

1. `kms_node_binding`。
2. 权限申请 featureCode。
3. 用户节点查询。
4. 目标访问校验。

验收：

1. 普通用户只能看到自己的节点。
2. 未授权目标节点不能发起会话。
3. 管理员审批后状态生效。

### Agent C：FISCO 合约与 chain-adapter

范围：

1. 新合约。
2. Java wrapper。
3. chain_outbox。
4. `key_chain_task/key_chain_result` 扩展。

验收：

1. 合约部署成功。
2. 三类证据能写链。
3. 失败能重试。
4. 旧 ENROLL/ROTATE/REVOKE 不受影响。

### Agent D：分发业务 API

范围：

1. 节点管理 API。
2. 会话 API。
3. 密钥池 API。
4. 消息 API。
5. 审计 API。

验收：

1. 会话能创建。
2. 密钥池能消费。
3. 消息能发送。
4. 链结果能回填。

### Agent E：生成算法接入

范围：

1. Go generator 新增 CL-Kyber/CL-Falcon。
2. Java 上链计算分支。
3. 前端生成选项。
4. key_value 大字段兼容。

验收：

1. 旧算法正常。
2. 新算法记录可保存。
3. 节点能绑定新算法公钥。

### Gemini F：`kms-user` 前端

范围：

1. 节点通信前台。
2. 我的节点。
3. 发起通信。
4. 会话与消息。
5. 密钥池状态。
6. 权限申请入口。

验收：

1. 用户体验不暴露运维概念。
2. 普通用户不能执行管理员操作。
3. 会话和密钥池方向表达清楚。

### Gemini G：分发管理员前端

范围：

1. 节点运维。
2. 绑定审批。
3. 密钥池运维。
4. 会话审计。
5. 链配置。

验收：

1. 管理员能力完整。
2. 页面不再出现 Ganache 术语。
3. 敏感字段脱敏。

### Agent H：生命周期联动

范围：

1. UPDATE/REVOKE 后会话失效。
2. 节点密钥版本。
3. `kms_session_invalidation`。
4. 链上会话状态变更。

验收：

1. 更新密钥后旧会话失效。
2. 回收密钥后节点相关会话不能继续使用。
3. 审计链路可追溯。

### Agent I：集成测试与验收

范围：

1. 端到端用户流程。
2. 管理员流程。
3. 链上证据。
4. 权限边界。
5. 回归旧生成/生命周期链路。

验收：

1. 用户 A 可通过绑定节点给用户 B 发起安全会话。
2. 预分发密钥池能被消费一次。
3. 消息摘要可上链。
4. 未授权用户不能访问目标节点。
5. 旧 SM2/SSCL、UPDATE、REVOKE 正常。

## 15. 风险清单

| 风险 | 等级 | 处理 |
|---|---|---|
| key_value 太短 | 高 | 升级 MEDIUMTEXT 或拆表 |
| 私钥/部分私钥落库 | 高 | 改为 ref/sealed handle |
| 用户和节点混淆 | 高 | 新增 node_binding |
| 普通用户获得管理员能力 | 高 | 用户前台和管理员后台拆分 |
| Falcon 语义混用 | 高 | Falcon 只作签名，CL-Falcon 标注研究型 |
| Ganache/FISCO 双链 | 高 | 删除 Ganache 路径，统一 FISCO |
| KeyEvidence 被塞爆 | 中高 | 新增 Node/Session/Message 合约 |
| Kafka action_type 混乱 | 中高 | 扩展 schema 和 idempotency_key |
| 消息逐条上链吞吐差 | 中 | 支持会话摘要聚合 |
| permission_request 字段不一致 | 中 | 先补 SQL/实体 |
| demo 缺页/字段 bug | 中 | 不照搬路由，重做页面 |
| 时间字段字符串化 | 中 | 新表用 DATETIME |

## 16. 最终验收场景

### 场景 1：用户节点绑定

1. 管理员创建节点 `node-a`。
2. 用户张三申请绑定 `node-a`。
3. 管理员审批通过。
4. 张三在 `kms-user` 的“我的节点”看到 `node-a`。
5. 张三不能看到其他未绑定节点。

### 场景 2：目标访问与会话建立

1. 李四绑定 `node-b`。
2. 张三申请访问李四的 `node-b`。
3. 管理员审批通过。
4. 张三选择 `node-a -> 李四 -> node-b`。
5. 系统检查密钥池。
6. 创建会话 `session-x`。
7. 会话证据写入 FISCO。

### 场景 3：预分发密钥池消费

1. 管理员为 `node-a -> node-b` 生成 100 条预分发密钥。
2. 张三创建会话时消费 1 条。
3. 该 key 状态从 `UNUSED` 变为 `USED`。
4. 再次创建会话不能重复使用同一 key。
5. 密钥池余量变为 99。

### 场景 4：安全消息发送

1. 张三在会话中发送消息。
2. 系统使用 AES-GCM 加密。
3. 数据库只保存密文和摘要。
4. 消息摘要写入 FISCO 或进入会话摘要聚合。
5. 用户前台只显示消息内容和链上摘要，不显示 session key。

### 场景 5：密钥更新导致会话失效

1. `node-b` 的通信密钥更新。
2. 生命周期系统记录 UPDATE。
3. 分发系统识别相关活动会话。
4. 旧会话状态变为 `INVALIDATED`。
5. 用户前台提示会话已失效，需要重新建立。
6. 链上记录会话状态变更。

## 17. 实施禁令

1. 禁止把 Django demo 作为长期服务并入系统。
2. 禁止普通用户页面出现节点注册、链配置、批量清理密钥池按钮。
3. 禁止保存明文私钥、明文部分私钥、明文预分发 AES key。
4. 禁止把完整大密文字段直接上链。
5. 禁止把 Node/Session/Message/PreDistributedKey 硬塞入 `keymanage`。
6. 禁止复用 demo 的 Ganache 合约作为 FISCO 合约。
7. 禁止静默降级到 demo crypto/fallback crypto。
8. 禁止不做 Service 层权限校验，只依赖前端隐藏按钮。

## 18. 推荐下一步

第一批实现前，先由一个 planner/architect agent 根据本文档产出三份短文档或 PRD：

1. `pqkds-domain-model.md`：最终领域模型和状态机。
2. `pqkds-api-contract.md`：前后端接口契约。
3. `pqkds-chain-contract.md`：FISCO 合约字段和事件。

随后再并行派发数据库、后端、合约、前端 Gemini、测试五条线。
