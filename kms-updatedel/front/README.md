# KMS 生命周期系统前端

密钥更新与回收生命周期系统前端，基于 Vue3 + Element Plus 构建。

## 页面访问说明

### 路由配置

| 页面 | 路由路径 | 说明 |
|------|----------|------|
| 首页 | `/index` | 系统首页 |
| 密钥更新 | `/lifecycle/keyupdate` | 密钥更新管理 |
| 密钥回收 | `/lifecycle/keydelete` | 密钥回收管理 |
| 密钥自动更新 | `/lifecycle/keyautoupdate` | 自动更新配置 |
| 用户密钥管理 | `/lifecycle/keyautoupdate/user` | 用户密钥自动更新管理 |
| 权限审批 | `/permission/request/index` | 权限申请审批 |

### 环境配置

开发环境使用端口 **5174**

```
VITE_APP_BASE_API = '/lifecycle-api'
```

代理配置：
- `/lifecycle-api` -> `http://localhost:9082` (生命周期 Java 后端)
- `/permission-api` -> `http://localhost:9082` (权限审批 Java 后端)

## 功能模块

### 1. 密钥更新 (Key Update)
- 密钥列表查询
- 密钥更新操作
- 支持多种加密算法类型

### 2. 密钥回收 (Key Delete)
- 密钥列表查询
- 密钥回收/删除操作
- 状态管理

### 3. 密钥自动更新 (Key Auto Update)
- 自动更新状态配置
- 批量启用/禁用自动更新
- 用户级别自动更新管理

### 4. 权限审批 (Permission Request)
- 权限申请列表
- 审批通过/拒绝
- 权限详情查看
- 权限回退

## 开发

```bash
# 安装依赖
npm install

# 开发模式启动
npm run dev

# 生产构建
npm run build:prod
```

## API 接口

API 文件位于 `src/api/` 目录：
- `lifecycle/lifecycle.js` - 生命周期相关 API
- `permission/permission.js` - 权限相关 API

## 项目结构

```
src/
├── api/                    # API 定义
│   ├── lifecycle/         # 生命周期 API
│   └── permission/       # 权限 API
├── assets/                # 静态资源
├── components/            # 公共组件
├── layout/               # 布局组件
├── plugins/              # 插件
├── router/               # 路由配置
├── store/                # 状态管理
├── utils/                # 工具函数
└── views/                # 页面视图
    ├── keyupdate/        # 密钥更新
    ├── keydelete/        # 密钥回收
    ├── keyautoupdate/    # 自动更新
    └── permission/       # 权限审批
```

## 许可证

MIT
