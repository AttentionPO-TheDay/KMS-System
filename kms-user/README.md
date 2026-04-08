# kms-user

统一普通用户前台。

## 当前定位

`kms-user` 负责统一普通用户入口，不替代各业务系统管理员后台。

当前目标：

1. 作为普通用户统一入口
2. 聚合生成、生命周期、分发三类日常能力
3. 提供权限申请、申请记录、回退入口
4. 保持 `kms-generate`、`kms-updatedel`、`kms-distribute` 后端独立

## 当前前端骨架

当前已落地的路由包括：

1. `/workbench`
2. `/generate`
3. `/lifecycle`
4. `/distribute`
5. `/permissions`

## 当前目录

1. `front/`：集成前端工程
2. `docs/`：集成迁移设计与实施文档

## 角色边界

1. 普通用户使用 `kms-user`
2. 生成系统管理员继续使用 `kms-generate/front`
3. 生命周期系统管理员继续使用 `kms-updatedel/front`
4. 分发管理员后台后续按需要补齐

## 参考文档

1. `doc/project_overview.md`
2. `doc/frontend-role-boundary.md`
3. `doc/user-permission-implementation.md`
4. `kms-user/docs/integration-plan.md`
