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

1. `front/`：生命周期系统管理员前端
2. `go-backend/`：Go 接入层，接收更新/回收请求并投递 Kafka
3. `java-backend/`：Java 业务层，消费更新/回收消息并执行轮换、回收、审批等逻辑
4. `docs/`：系统设计与接口文档
5. `sql/`：权限申请等数据库脚本

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
6. `GET /permission/request/list`
7. `GET /permission/request/{requestId}`
8. `POST /permission/request/submit`
9. `PUT /permission/request/approve/{requestId}`
10. `PUT /permission/request/reject/{requestId}`
11. `PUT /permission/request/rollback/{requestId}`
12. `DELETE /permission/request/{requestId}`

默认端口：`9082`

## 当前消息链路

1. Go 接入层接收 `UPDATE_KEY` / `REVOKE_KEY`
2. 更新消息投递到 `key_update_log`
3. 回收消息投递到 `key_revoke_log`
4. Java `LifecycleKafkaConsumer` 统一消费更新和回收消息
5. Java 业务层执行轮换、回收、自动更新配置和权限处理
6. 链同步相关后续处理由 `UpdatedelChainConsumer` 负责

## 说明

1. `front/` 当前仍保留权限审批和系统管理能力
2. 普通用户主入口已经迁移到 `kms-user`
3. 生命周期管理员后台仍然保留为独立前端

## 参考文档

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-updatedel/docs/migration-map.md`
4. `doc/user-permission-implementation.md`
