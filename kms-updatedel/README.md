# kms-updatedel

密钥更新与回收系统。

## 当前定位

负责以下能力：

1. 密钥更新
2. 密钥回收
3. 自动更新配置
4. 生命周期查询
5. 权限申请、审批、回退
6. 更新/回收事件消费与后续上链

## 当前目录

1. `front/`：生命周期系统前端
2. `go-backend/`：Go 接入层，接收更新/回收请求并投递 Kafka
3. `java-backend/`：Java 业务层，消费更新/回收消息并执行轮换、回收、审批等逻辑
4. `docs/`：系统设计与接口文档
5. `sql/`：权限申请等数据库脚本
6. `tests/`：联调与压测脚本

## 当前接口口径

### Go 接入层

1. `POST /lifecycle/request/UPDATE_KEY`
2. `POST /lifecycle/request/REVOKE_KEY`
3. `GET /lifecycle/ping`
4. `GET /lifecycle/metrics`

默认端口：`8082`

### Java 业务层

1. `GET /lifecycle/keymanage/list`
2. `GET /lifecycle/keymanage/{keyId}`
3. `PUT /lifecycle/keymanage`
4. `PUT /lifecycle/keymanage/auto-update`
5. `DELETE /lifecycle/keymanage/{keyId}`
6. `POST /permission/request/submit`
7. `GET /permission/request/list`
8. `GET /permission/request/{requestId}`
9. `PUT /permission/request/approve/{requestId}`
10. `PUT /permission/request/reject/{requestId}`
11. `PUT /permission/request/rollback/{requestId}`

默认端口：`9082`

## 当前消息链路

1. Go 接入层接收 `UPDATE_KEY` / `REVOKE_KEY`
2. 更新消息投递到 `key_update_log`
3. 回收消息投递到 `key_revoke_log`
4. Java `UpdateKafkaConsumer` / `RevokeKafkaConsumer` 分别消费
5. Java 业务层执行轮换、回收、自动更新配置和权限处理

## 参考文档

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-updatedel/docs/migration-map.md`
4. `doc/user-permission-implementation.md`
