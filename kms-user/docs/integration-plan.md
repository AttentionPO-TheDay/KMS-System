# kms-user 集成前端实施方案

## 1. 目标

`kms-user` 作为统一用户界面，承接原老系统中的集成式操作体验，但不回退为单体系统。

核心原则：

1. 前端集成，后端拆分
2. 统一入口，统一导航，统一工作台
3. 业务接口按系统边界分别访问
4. 先迁页面，再逐步收敛认证与菜单
5. 普通用户前台统一，管理员后台按系统保留
6. 普通用户的受限功能采用申请审批模式，不直接暴露后台权限

## 1.1 用户分层原则

`kms-user` 的定位是统一普通用户入口，不替代各业务系统管理员后台。

角色边界如下：

1. 普通用户
   - 使用 `kms-user` 完成注册、登录、生成、更新、回收、分发查询等日常操作
   - 对受限功能可在 `kms-user` 内发起权限申请
   - 原 `kms-generate/front`、`kms-updatedel/front` 中面向普通用户的页面逐步迁出或下线
2. 临时授权用户
   - 仍然使用 `kms-user`
   - 通过申请审批后，在限定范围内临时获得更高功能权限
   - 操作完成后回退为普通用户
3. 生成系统管理员
   - 继续使用 `kms-generate/front`
   - 负责生成链路配置、生成记录管理、审计、生成域权限审批与生成侧运维操作
4. 生命周期系统管理员
   - 继续使用 `kms-updatedel/front`
   - 负责更新、回收、自动更新、生命周期域权限审批、回退等后台操作
5. 分发系统管理员
   - 后续如形成独立后台，按分发系统单独保留，并在分发后台内处理分发域审批

该分层下，统一的是账号、角色、用户身份；不统一的是所有管理页面。

## 2. 系统边界

### 2.1 生成系统

来源：`kms-generate`

承载能力：

1. 用户注册
2. 公共参数查询
3. 密钥生成
4. 生成历史查询
5. 我的密钥查询
6. 生成系统后台管理
7. 生成域权限申请与审批

API 前缀：`/generate-api`

### 2.2 生命周期系统

来源：`kms-updatedel`

承载能力：

1. 密钥更新
2. 密钥回收
3. 自动更新配置
4. 权限申请与审批
5. 生命周期系统后台管理
6. 生命周期域临时提权审批与回退

API 前缀：`/lifecycle-api`

### 2.3 分发系统

来源：`kms-distribute`

承载能力：

1. 分发记录查询
2. 分发详情查看
3. 分发系统后台管理（后续补齐）
4. 分发域权限申请与审批（后续补齐）

API 前缀：`/distribute-api`

## 3. 页面迁移映射

说明：本节仅针对普通用户前台迁移，不包含管理员后台迁移。管理员后台继续保留在各业务系统独立前端中。

### 3.1 老系统来源

优先参考以下页面：

1. `legacy-kms/RuoYi-Vue3-master/src/views/userKeys.vue`
2. `legacy-kms/RuoYi-Vue3-master/src/views/keygenerate/index.vue`
3. `legacy-kms/RuoYi-Vue3-master/src/views/keyupdate/index.vue`
4. `legacy-kms/RuoYi-Vue3-master/src/views/keydelete/index.vue`
5. `legacy-kms/RuoYi-Vue3-master/src/views/keyautoupdate/index.vue`
6. `legacy-kms/RuoYi-Vue3-master/src/views/permission/request/index.vue`

### 3.2 新前端映射

1. `kms-user/front/src/views/workbench/WorkbenchView.vue`
   承接老系统集成操作台
2. `kms-user/front/src/views/generate/GenerateView.vue`
   承接密钥生成主流程
3. `kms-user/front/src/views/lifecycle/LifecycleView.vue`
   承接更新、回收、自动更新与权限流程
4. `kms-user/front/src/views/distribute/DistributeView.vue`
   承接分发记录查询
5. `kms-user/front` 中新增权限申请、我的申请记录、回退入口

### 3.3 管理员后台保留策略

1. `kms-generate/front`
   保留为生成系统管理员后台，不作为普通用户主入口，并负责生成域申请审批
2. `kms-updatedel/front`
   保留为生命周期系统管理员后台，不作为普通用户主入口，并负责生命周期域申请审批
3. `kms-distribute/front`
   当前仅有页面片段，后续按是否存在独立管理员需求决定是否建设独立后台，并在该后台内处理分发域审批

## 4. 推荐实施顺序

1. 先在 `kms-user/front` 内完成统一导航与工作台
2. 迁入 `kms-generate/front` 中面向普通用户的生成页面和 API
3. 迁入 `kms-updatedel/front` 中面向普通用户的生命周期页面和 API
4. 将 `kms-distribute/front/src/views/distribute/record.vue` 纳入统一前端
5. 统一登录、用户信息和普通用户菜单
6. 在 `kms-user` 中实现权限申请、申请记录、回退入口
7. 保留各系统管理员后台入口和系统级菜单
8. 在对应系统后台中实现对应域的审批页面

## 5. 当前阻塞项

1. `kms-updatedel/java-backend` 业务接口尚未完整落地
2. 三套后端的统一登录与菜单能力尚未收敛
3. 分发前端目前只有页面片段，尚不是完整工程
4. 管理员后台与普通用户前台的菜单边界尚未显式建模
5. 各系统审批流与临时提权回退规则尚未统一建模

## 6. 下一步实现项

1. 引入统一登录页与 token 管理
2. 把工作台改造成真实的操作流入口
3. 将生成页面从 `kms-generate/front` 迁入 `kms-user/front`
4. 抽象三套 API 客户端
5. 统一错误码、分页结构和用户信息模型
6. 将普通用户菜单与管理员菜单拆分建模
7. 为管理员提供跳转到各业务后台的独立入口
8. 在 `kms-user` 中复用旧版的权限不足提示、申请、回退交互模式
9. 将审批责任固定到对应业务系统后台

## 7. 目标形态

最终推荐形态如下：

1. 普通用户
   - 只访问 `kms-user`
   - 只注册一次账号
   - 共享同一套 `sys_user` / `sys_role` 身份
   - 对受限功能可在统一前台发起临时提权申请
2. 管理员
   - 根据职责访问 `kms-generate/front`、`kms-updatedel/front` 或后续的分发后台
   - 共用同一套用户体系，但使用各系统独立后台
   - 只在对应系统后台处理本系统的审批申请
3. 后端
   - 继续保持 `kms-generate`、`kms-updatedel`、`kms-distribute` 独立部署
   - 不因前台统一而回退到单体工程

## 8. 旧版能力继承原则

权限申请与审批流程参考旧版实现，保留以下关键交互：

1. 普通用户访问受限功能时提示权限不足
2. 可直接跳转到权限申请表单
3. 申请需填写申请理由
4. 审批通过后获得临时权限
5. 操作完成后支持手动回退或自动回退

但审批入口不再放在统一普通用户前台，而是固定在对应系统的管理员后台内处理。

## 9. 第一阶段申请功能清单

需要申请的功能范围优先参考旧版已落地能力，当前先收敛为以下两项：

1. 生成域 `查看公共密钥列表`
   - 来源参考：`legacy-kms/RuoYi-Vue3-master/src/views/userKeys.vue`
   - 旧版要求 `role_level <= 1`
   - 在新架构中由用户在 `kms-user` 发起申请，在 `kms-generate/front` 审批
2. 生命周期域 `密钥自动更新`
   - 来源参考：`legacy-kms/RuoYi-Vue3-master/src/views/userKeys.vue`
   - 旧版要求 `role_level = 0`
   - 在新架构中由用户在 `kms-user` 发起申请，在 `kms-updatedel/front` 审批

实施约束：

1. 第一阶段不要额外扩展更多申请项
2. 其他功能默认按普通权限模型处理
3. 若后续新增申请项，必须明确功能归属系统、目标权限等级、审批人和回退规则
