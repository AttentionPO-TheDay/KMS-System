# 用户、权限与审批实现说明

## 1. 目的

本文件用于固化当前仓库在用户体系、前端入口、权限申请、审批回退上的最终实现口径，避免后续开发继续依赖历史对话结论。

适用范围：

1. `kms-user`
2. `kms-generate`
3. `kms-updatedel`
4. `kms-distribute`

## 2. 最终口径

### 2.1 用户入口

1. 普通用户只使用 `kms-user`
2. 生成系统管理员使用 `kms-generate/front`
3. 生命周期系统管理员使用 `kms-updatedel/front`
4. 分发系统管理员后续按需要建设独立后台

### 2.2 用户体系

1. 三套系统共用一套用户体系
2. 用户只注册一次
3. 同一用户在三套系统中保持同一身份
4. 管理后台不单独维护一套用户

### 2.3 提权模型

1. 普通用户默认仅具备普通功能权限
2. 对受限功能采用申请审批模型
3. 审批通过后，用户临时获得更高权限
4. 操作完成后，权限回退
5. 不采用“普通用户永久升级为管理员”的模型

## 3. 旧版实现参考

旧版核心实现参考以下位置：

1. 前端申请入口
   - `legacy-kms/RuoYi-Vue3-master/src/views/userKeys.vue`
2. 前端申请 API
   - `legacy-kms/RuoYi-Vue3-master/src/api/permission/permission.js`
3. 后端审批控制器
   - `legacy-kms/ruoyi-admin/src/main/java/com/ruoyi/permission/controller/PermissionRequestController.java`
4. 后端审批服务
   - `legacy-kms/ruoyi-system/src/main/java/com/ruoyi/permission/service/impl/PermissionRequestServiceImpl.java`
5. 自动回退定时任务
   - `legacy-kms/ruoyi-system/src/main/java/com/ruoyi/permission/task/PermissionRevokeTask.java`
6. 申请表结构
   - `legacy-kms/sql/6_permission_request.sql`

### 3.1 旧版角色等级

旧版采用 `role_level`：

1. `0`：管理员
2. `1`：中级用户
3. `2`：普通用户

### 3.2 旧版申请链路

1. 普通用户访问受限功能
2. 前端弹出权限不足提示
3. 用户填写申请理由并提交
4. 管理员进入审批页通过或拒绝
5. 通过后后端直接更新 `sys_user.role_level`
6. 用户刷新 `getInfo` 获得最新等级
7. 操作完成后手动回退或等待自动回退

### 3.3 旧版第一手申请功能

旧版明确落地的申请功能只有两项：

1. `查看公共密钥列表`
   - 需要 `role_level <= 1`
2. `密钥自动更新`
   - 需要 `role_level = 0`

本次新架构实现以这两项为第一阶段基准，不额外扩散申请范围。

## 4. 新架构实现方式

### 4.1 普通用户前台

`kms-user` 负责：

1. 登录
2. 注册
3. 工作台
4. 密钥生成、生成记录、公共库与公共参数查询
5. 更新、回收、自动更新
6. 单条密钥安全分析与结果回执
7. 分发记录查询
8. 权限不足提示
9. 权限申请入口
10. 我的申请记录
11. 权限回退入口

`kms-user` 不负责：

1. 审批后台
2. 系统管理后台
3. 系统运维后台
4. 管理员菜单配置页

### 4.2 管理员后台

`kms-generate/front` 负责：

1. 生成域后台管理
2. 生成域申请审批
3. 生成记录、配置、审计
4. 算法图解与演示

`kms-updatedel/front` 负责：

1. 生命周期后台管理
2. 生命周期域申请审批
3. 更新、回收、自动更新、安全分析、回退

`kms-distribute` 后续负责：

1. 分发后台管理
2. 分发域申请审批

### 4.3 审批归属

审批必须按系统归属处理：

1. 生成域申请在 `kms-generate` 审批
2. 生命周期域申请在 `kms-updatedel` 审批
3. 分发域申请在分发后台审批

禁止做法：

1. 在 `kms-user` 中直接做管理员审批
2. 一个系统后台审批另一个系统的功能申请

## 5. 第一阶段申请项

### 5.1 查看公共密钥列表

1. 所属系统：生成域
2. 申请入口：`kms-user`
3. 审批入口：`kms-generate/front`
4. 目标权限：`role_level = 1`
5. 回退目标：`role_level = 2`

### 5.2 密钥自动更新

1. 所属系统：生命周期域
2. 申请入口：`kms-user`
3. 审批入口：`kms-updatedel/front`
4. 目标权限：`role_level = 0`
5. 回退目标：回到申请前等级，通常为 `role_level = 2`

## 6. 数据模型建议

### 6.1 用户表

继续复用共享 `sys_user`，保留 `role_level` 字段：

1. `0`：管理员
2. `1`：临时授权用户/中级用户
3. `2`：普通用户

### 6.2 申请表

建议新架构继续保留独立申请表，字段至少包括：

1. `request_id`
2. `user_id`
3. `user_name`
4. `system_code`
5. `feature_code`
6. `original_level`
7. `request_level`
8. `request_reason`
9. `status`
10. `is_temp`
11. `request_time`
12. `approve_by`
13. `approve_time`
14. `approve_note`
15. `rollback_time`

相比旧版，新增 `system_code` 和 `feature_code`，用于把审批责任明确绑定到业务域。

## 7. 接口边界建议

### 7.1 普通用户前台接口

由 `kms-user` 调用对应业务后端：

1. `POST /permission/request/submit`
2. `GET /permission/request/list`
3. `PUT /permission/request/rollback/{requestId}`

### 7.2 管理员后台接口

由各系统后台调用各自后端：

1. `GET /permission/request/list`
2. `GET /permission/request/{requestId}`
3. `PUT /permission/request/approve/{requestId}`
4. `PUT /permission/request/reject/{requestId}`

后续如果按系统拆接口前缀，建议保留统一资源名，但走各系统自己的 API 前缀。

## 8. 不做的事情

第一阶段明确不做：

1. 真正单点登录中心
2. 把所有管理员菜单并入 `kms-user`
3. 所有高权限功能都改成申请模式
4. 普通用户永久升级为管理员
5. 在统一前台里做跨系统后台管理

## 9. 开发顺序

1. 统一普通用户入口到 `kms-user`
2. 保留 `kms-generate/front` 和 `kms-updatedel/front` 管理后台
3. 先实现两类申请项
4. 将审批责任分别落到对应系统后台
5. 补齐申请记录、回退、自动回退
6. 最后再考虑是否扩展更多申请项

## 10. 验收标准

1. 普通用户在 `kms-user` 注册一次即可使用普通功能
2. 普通用户在 `kms-user` 可以申请 `查看公共密钥列表`
3. 该申请只能在 `kms-generate/front` 审批
4. 普通用户在 `kms-user` 可以申请 `密钥自动更新`
5. 该申请只能在 `kms-updatedel/front` 审批
6. 审批通过后用户可临时获得目标能力
7. 操作完成后可手动回退或自动回退
8. 管理员后台继续保留且不被统一前台替代
