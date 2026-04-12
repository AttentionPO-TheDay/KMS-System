# kms-distribute

密钥分发系统。

## 当前定位

负责分发记录相关能力，同时消费生成、更新、回收以及上链结果事件，沉淀并回填分发记录。

## 当前目录

1. `front/`：独立 Vue3 + Vite 前端工程，可单独联调分发后端
2. `java-backend/`：Java 业务服务与 Kafka 消费者
3. `sql/`：分发记录表脚本

## 当前 Java 接口

1. `GET /distribute/record/list`
2. `POST /distribute/record/export`
3. `GET /distribute/record/{recordId}`
4. `POST /distribute/record`
5. `POST /distribute/record/batch`
6. `PUT /distribute/record`
7. `DELETE /distribute/record/{recordId}`

默认端口：`8083`

## 当前前端状态

1. `front/` 已具备独立登录、路由、分发记录查询、导出和详情查看能力
2. 开发环境默认通过 `/distribute-api` 代理到 `http://localhost:8083`
3. 当前详情以记录页内对话框呈现，不是独立详情路由

## 当前消息链路

后端会消费以下 Kafka topic：

1. `key_generate_log`
2. `key_update_log`
3. `key_revoke_log`
4. `key_chain_result`

主要用途：

1. 自动写入生成、更新、回收对应的分发记录
2. 在上链完成后消费 `key_chain_result` 回填链哈希、区块高度和备注
3. 为统一前台和独立分发前端提供查询基础

## 参考文档

1. `doc/project_overview.md`
2. `kms-user/docs/integration-plan.md`
