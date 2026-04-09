# kms-user 集成前端实施说明

## 1. 文档定位

本文档说明 `kms-user` 在当前仓库中的实际集成口径，重点描述已经落地的普通用户前台能力，而不是早期规划状态。

## 2. 当前定位

`kms-user` 是统一普通用户入口，不替代各业务系统管理员后台。

角色边界如下：

1. 普通用户使用 `kms-user` 完成注册、登录、生成、更新、回收、分发查询和权限申请等日常操作
2. 临时授权用户仍然使用 `kms-user`，但仅在获批能力范围内临时提权
3. 生成系统管理员继续使用 `kms-generate/front`
4. 生命周期系统管理员继续使用 `kms-updatedel/front`
5. 分发系统如果后续形成独立管理员后台，应继续按系统边界单独建设

## 3. 当前系统边界

### 3.1 生成系统

来源：`kms-generate`

当前由 `kms-user` 集成的普通用户能力：

1. 生成记录查询
2. 公共参数查询
3. 公共密钥相关受限能力申请入口

API 前缀：`/generate-api`

### 3.2 生命周期系统

来源：`kms-updatedel`

当前由 `kms-user` 集成的普通用户能力：

1. 密钥更新
2. 密钥回收
3. 自动更新开关与查询
4. 自动更新受限能力申请入口

API 前缀：`/lifecycle-api`

### 3.3 分发系统

来源：`kms-distribute`

当前由 `kms-user` 集成的普通用户能力：

1. 分发记录查询
2. 分发详情查看

API 前缀：`/distribute-api`

## 4. 当前页面映射

1. `src/views/workbench/WorkbenchView.vue`
   - 保留集成式工作台能力
2. `src/views/generate/GenerateView.vue`
   - 承接生成记录与公共参数相关用户侧查询
3. `src/views/lifecycle/LifecycleView.vue`
   - 承接更新、回收、自动更新与相关权限流程
4. `src/views/distribute/DistributeView.vue`
   - 承接分发记录查询与详情查看
5. `src/views/permissions/PermissionView.vue`
   - 承接权限申请、记录聚合与回退

## 5. 当前路由口径

当前已落地的主要路由包括：

1. `/workbench`
2. `/generate`
3. `/updatedel`
4. `/lifecycle`
   - 当前作为到 `/updatedel` 的兼容跳转
5. `/distribute`
6. `/permissions`
7. `/login`
8. `/register`
9. `/user/profile`

## 6. 当前权限申请口径

当前统一前台聚焦两类申请项：

1. `PUBLIC_KEY_LIST`
   - 由生成系统管理员审批
2. `AUTO_UPDATE`
   - 由生命周期系统管理员审批

约束：

1. `kms-user` 只负责用户发起申请、展示记录、执行回退
2. `kms-user` 不直接承担管理员审批职责
3. 审批必须在对应业务系统管理员后台完成

## 7. 当前开发说明

1. `kms-user` 已按系统边界拆分 API 客户端，不回退为单体后端
2. `WorkbenchView.vue` 仍保留较强的一体化操作能力
3. 新的主体验路径已经收敛到按功能拆分的独立页面

## 8. 参考文档

1. `doc/project_overview.md`
2. `doc/frontend-role-boundary.md`
3. `doc/user-permission-implementation.md`
