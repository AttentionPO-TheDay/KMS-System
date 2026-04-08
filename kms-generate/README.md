# kms-generate

密钥生成系统。

## 当前定位

负责以下能力：

1. 用户注册
2. 公共参数获取
3. 密钥生成接入
4. 生成结果查询
5. 生成记录入库
6. 生成事件上链
7. 生成域权限申请与审批

## 当前目录

1. `front/`：生成系统前端
2. `go-backend/`：高吞吐 Go 接入层，接收生成请求并投递 Kafka
3. `java-backend/`：Java 业务层，消费 `key_generate_log` 并完成入库、审计、上链任务投递
4. `docs/`：生成系统设计与迁移文档
5. `tests/`：联调与压测脚本

## 当前接口口径

### Go 接入层

1. `POST /generate/request/Register`
2. `POST /generate/request/ENROLL_KEY`
3. `POST /generate/request/REENROLL_KEY`
4. `POST /generate/request/comparam`
5. `GET /generate/ping`

默认端口：`8081`

### Java 业务层

1. `GET /generate/key/list`
2. `GET /generate/key/{keyId}`
3. `GET /generate/key/chain/{keyId}`
4. `POST /generate/user/register`
5. `GET /generate/user/profile`
6. `GET/POST/PUT/DELETE /generate/keymanage/*`
7. `GET/POST/PUT /permission/request/*`

默认端口：`9081`

## 当前消息链路

1. Go 接入层接收生成请求
2. Go 接入层将消息投递到 `key_generate_log`
3. Java `GenerateKafkaConsumer` 消费该 topic
4. Java 完成批量入库、审计记录、上链任务投递
5. 后续链同步消费者处理 `key_chain_task`

## 参考文档

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-generate/front/README.md`
4. `kms-generate/docs/migration-map.md`
