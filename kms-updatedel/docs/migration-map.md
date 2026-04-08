# kms-updatedel 文档

此目录用于存放 kms-updatedel（密钥更新与回收系统）的设计与接口文档。

## 当前已补齐的最小闭环

1. Go 接入层接收 `UPDATE_KEY` / `REVOKE_KEY` 并投递 Kafka。
2. Java 业务层消费 `key_update_log` / `key_revoke_log`，完成密钥轮换与逻辑回收。
3. Java 业务层提供生命周期查询、自动更新状态修改、权限申请/审批/回退接口。
4. 定时任务每分钟扫描一次已审批且超出 30 分钟的临时权限，并自动回退。

## 已落地接口

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

## 数据与消息约定

1. 密钥主表继续复用旧系统 `keymanage`。
2. 权限申请表脚本位于 `kms-updatedel/sql/1_permission_request.sql`。
3. Kafka 更新 topic: `key_update_log`
4. Kafka 回收 topic: `key_revoke_log`
5. 上链任务 topic: `key_chain_task`

## 参考

1. 旧 Java 实现：`legacy-kms/ruoyi-admin/src/main/java/com/ruoyi/keymanage`
2. 旧权限实现：`legacy-kms/ruoyi-system/src/main/java/com/ruoyi/permission`
3. 旧前端页面：`legacy-kms/RuoYi-Vue3-master/src/views/keyupdate`、`keydelete`、`keyautoupdate`、`permission`
