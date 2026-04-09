# kms-user

统一普通用户前台。

## 当前定位

`kms-user` 是普通用户统一入口，不替代各业务系统管理员后台。

当前目标：

1. 作为普通用户统一入口
2. 聚合生成、生命周期、分发三类日常能力
3. 提供权限申请、申请记录、回退入口
4. 保持 `kms-generate`、`kms-updatedel`、`kms-distribute` 后端独立

## 当前已实现能力

当前已实现的页面和能力包括：

1. `/workbench` 统一工作台
2. `/generate` 生成记录查询与公共参数查询
3. `/updatedel` 密钥更新、回收、自动更新配置
4. `/distribute` 分发记录查询与详情查看
5. `/permissions` 权限申请、记录聚合与回退
6. `/login`、`/register`、`/user/profile`

其中权限申请当前聚焦两类受限能力：

1. `PUBLIC_KEY_LIST`
2. `AUTO_UPDATE`

## 当前目录

1. `front/`：统一前端工程
2. `docs/`：集成迁移设计与实施文档

## 后端接入方式

前端已按系统边界拆分 API 客户端：

1. `/generate-api` -> 生成系统后端
2. `/lifecycle-api` -> 生命周期系统后端
3. `/distribute-api` -> 分发系统后端

## 角色边界

1. 普通用户使用 `kms-user`
2. 生成系统管理员继续使用 `kms-generate/front`
3. 生命周期系统管理员继续使用 `kms-updatedel/front`
4. 分发系统如果后续需要独立管理员后台，应单独明确其角色边界与审批归属

## 当前说明

1. `WorkbenchView.vue` 仍保留集成式工作台能力
2. 新的主路径是按功能拆分的 `/generate`、`/updatedel`、`/distribute`、`/permissions`
3. 普通用户权限审批不在 `kms-user` 完成，而是在对应业务系统管理员后台完成

## 参考文档

1. `doc/project_overview.md`
2. `doc/frontend-role-boundary.md`
3. `doc/user-permission-implementation.md`
4. `kms-user/docs/integration-plan.md`
