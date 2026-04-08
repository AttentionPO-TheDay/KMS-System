# kms-distribute

密钥分发系统。

## 当前定位

负责分发记录相关能力，当前重点是分发记录的查询和维护。

## 当前目录

1. `front/`：前端页面片段，尚未形成完整独立工程
2. `java-backend/`：Java 业务服务
3. `sql/`：分发记录表脚本

## 当前 Java 接口

1. `GET /distribute/record/list`
2. `GET /distribute/record/{recordId}`
3. `POST /distribute/record`
4. `POST /distribute/record/batch`
5. `PUT /distribute/record`
6. `DELETE /distribute/record/{recordId}`

默认端口：`8083`

## 当前状态说明

1. Java 后端接口已经落地
2. `front/` 当前仍是页面片段，不是完整前端工程
3. 后续如果需要分发管理员后台，应单独明确其角色边界与审批归属

## 参考文档

1. `doc/project_overview.md`
2. `kms-user/docs/integration-plan.md`
