# Falcon-KDS2 系统完整API接口列表

## 系统概述
- **系统名称**：Falcon-KDS2（后量子密码学密钥分发系统）
- **基础URL**：http://localhost:8000/api/
- **认证方式**：JWT Token
- **API版本**：v1

## 认证接口

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | /api/login/ | 用户登录 |
| POST | /api/logout/ | 用户登出 |
| POST | /token/refresh/ | Token刷新 |
| GET | /api/captcha/ | 验证码获取 |
| POST | /apiLogin/ | API登录 |
| POST | /api/token/ | Token获取 |

## 系统参数接口 (/api/pqkds/system-parameters/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 列表查询 |
| GET | /{id}/ | 详情查询 |
| POST | / | 创建参数 |
| PUT | /{id}/ | 更新参数 |
| DELETE | /{id}/ | 删除参数 |
| POST | /initialize/ | 系统初始化 |
| GET | /active/ | 获取活跃参数 |
| POST | /generate_kyber_partial_key/ | 生成Kyber部分私钥 |
| POST | /generate_falcon_partial_key/ | 生成Falcon部分私钥 |
| POST | /generate_all_partial_keys/ | 生成所有部分私钥 |

## 节点管理接口 (/api/pqkds/nodes/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 节点列表 |
| GET | /{id}/ | 节点详情 |
| POST | / | 创建节点 |
| PUT | /{id}/ | 更新节点 |
| DELETE | /{id}/ | 删除节点 |
| POST | /batch_delete/ | 批量删除 |
| POST | /register/ | 节点注册 |
| POST | /{id}/generate_kyber_keys/ | 生成Kyber密钥 |
| POST | /{id}/generate_falcon_keys/ | 生成Falcon密钥 |
| POST | /{id}/generate_falcon_keys_v2/ | 生成Falcon密钥V2 |
| POST | /{id}/generate_falcon_keypair/ | 生成Falcon密钥对 |
| GET | /{id}/keys/ | 获取节点密钥 |
| GET | /{id}/key_details/ | 获取密钥详情 |
| POST | /{id}/update_keys/ | 更新密钥 |
| GET | /{id}/stats/ | 获取统计 |
| GET | /{id}/get_public_keys/ | 获取公钥 |
| POST | /discover_node/ | 节点发现 |
| POST | /{id}/prepare_key_negotiation/ | 准备密钥协商 |
| POST | /cleanup_blockchain_data/ | 清理区块链数据 |

## 区块链接口 (/api/pqkds/blocks/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 区块列表 |
| GET | /{id}/ | 区块详情 |
| POST | / | 创建区块 |
| PUT | /{id}/ | 更新区块 |
| DELETE | /{id}/ | 删除区块 |

## 交易接口 (/api/pqkds/transactions/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 交易列表 |
| GET | /{id}/ | 交易详情 |
| POST | / | 创建交易 |
| PUT | /{id}/ | 更新交易 |
| DELETE | /{id}/ | 删除交易 |
| GET | /by_type/ | 按类型查询 |

## 会话密钥接口 (/api/pqkds/session-keys/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 会话列表 |
| GET | /{id}/ | 会话详情 |
| POST | / | 创建会话 |
| PUT | /{id}/ | 更新会话 |
| DELETE | /{id}/ | 删除会话 |
| POST | /batch_delete/ | 批量删除 |
| GET | /stats/ | 获取统计 |
| POST | /initiate_kyber_agreement/ | 启动Kyber协商 |
| POST | /complete_kyber_agreement/ | 完成Kyber协商 |
| POST | /initiate_falcon_verification/ | 启动Falcon验证 |
| POST | /complete_falcon_verification/ | 完成Falcon验证 |
| GET | /{id}/get_session_details/ | 获取会话详情 |
| POST | /verify_session_key/ | 验证会话密钥 |
| POST | /cleanup_expired_sessions/ | 清理过期会话 |
| POST | /validate_all_active_sessions/ | 验证所有活跃会话 |

## 消息接口 (/api/pqkds/messages/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 消息列表 |
| GET | /{id}/ | 消息详情 |
| POST | / | 创建消息 |
| PUT | /{id}/ | 更新消息 |
| DELETE | /{id}/ | 删除消息 |
| POST | /batch_delete/ | 批量删除 |
| GET | /stats/ | 获取统计 |
| POST | /send_message/ | 发送消息 |
| GET | /receive_messages/ | 接收消息 |
| POST | /verify_message_signature/ | 验证签名 |

## 区块链配置接口 (/api/pqkds/blockchain-config/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 配置列表 |
| GET | /{id}/ | 配置详情 |
| POST | / | 创建配置 |
| PUT | /{id}/ | 更新配置 |
| DELETE | /{id}/ | 删除配置 |
| POST | /test_connection/ | 测试连接 |
| POST | /sync_data/ | 同步数据 |

## Falcon密钥对接口 (/api/pqkds/falcon-keypairs/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 密钥对列表 |
| GET | /{id}/ | 密钥对详情 |
| POST | / | 创建密钥对 |
| PUT | /{id}/ | 更新密钥对 |
| DELETE | /{id}/ | 删除密钥对 |

## 密钥分发日志接口 (/api/pqkds/logs/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 日志列表 |
| GET | /{id}/ | 日志详情 |
| POST | / | 创建日志 |
| PUT | /{id}/ | 更新日志 |
| DELETE | /{id}/ | 删除日志 |
| GET | /stats/ | 获取统计 |

## 系统统计接口 (/api/pqkds/stats/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 统计列表 |
| GET | /{id}/ | 统计详情 |
| POST | / | 创建统计 |
| PUT | /{id}/ | 更新统计 |
| DELETE | /{id}/ | 删除统计 |
| GET | /system_stats/ | 系统统计 |
| GET | /node_stats/ | 节点统计 |
| GET | /blockchain_stats/ | 区块链统计 |

## 聊天接口 (/api/pqkds/chat/)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | / | 聊天页面 |
| POST | /send-message/ | 发送消息 |
| GET | /messages/ | 获取消息 |
| GET | /nodes/ | 获取节点列表 |

## 其他接口

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | /api/pqkds/node/generate-falcon-keypair/ | 生成Falcon密钥对 |
| POST | /api/pqkds/node/save-falcon-keys/ | 保存Falcon密钥 |
| GET | /api/pqkds/falcon/verify/{node_id}/ | 获取并验证公钥 |
| POST | /api/pqkds/falcon/verify-integrity/ | 验证公钥完整性 |
| POST | /api/pqkds/falcon/batch-verify/ | 批量验证公钥 |

## 系统管理接口 (/api/system/)

- 菜单管理：/menu/
- 菜单按钮：/menu_button/
- 角色管理：/role/
- 部门管理：/dept/
- 用户管理：/user/
- 操作日志：/operation_log/
- 字典管理：/dictionary/
- 地区管理：/area/
- 文件管理：/file/
- API白名单：/api_white_list/
- 系统配置：/system_config/
- 消息中心：/message_center/
- 角色菜单权限：/role_menu_permission/
- 角色菜单按钮权限：/role_menu_button_permission/
- 菜单字段：/column/

## 初始化接口

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /api/init/dictionary/ | 初始化字典 |
| GET | /api/init/settings/ | 初始化系统设置 |

## API文档

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /swagger/ | Swagger UI |
| GET | /swagger.json | Swagger JSON |
| GET | /redoc/ | ReDoc |

## 通用查询参数

所有列表接口都支持：
- page: 页码（默认1）
- limit: 每页数量（默认10）
- search: 搜索关键词
- ordering: 排序字段

## 认证方式

所有需要认证的接口都需要在请求头中添加：
```
Authorization: Bearer <JWT_TOKEN>
```

## 通用响应格式

**成功响应**：
```json
{
    "code": 200,
    "msg": "操作成功",
    "data": {...}
}
```

**错误响应**：
```json
{
    "code": 400,
    "msg": "错误信息",
    "data": null
}
```

