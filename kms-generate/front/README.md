# KMS Generate Front - 密钥生成系统前端

## 项目说明

基于 RuoYi-Vue3 构建的密钥生成系统前端项目，仅承载生成相关前端能力。

## 目录结构

```
kms-generate/front/
├── src/
│   ├── api/                    # API 接口定义
│   │   ├── generate/           # 生成系统 API (keymanage)
│   │   ├── login.js            # 登录注册 API
│   │   ├── menu.js             # 菜单 API
│   │   └── system/user.js      # 用户 API
│   ├── views/                  # 页面视图
│   │   ├── generate/           # 密钥生成页面
│   │   ├── generateHistory/    # 生成历史页面
│   │   ├── commonParam/        # 公共参数页面
│   │   ├── userKeys/           # 用户密钥列表
│   │   ├── login/              # 登录页
│   │   ├── register/           # 注册页
│   │   ├── index/              # 首页
│   │   ├── publickeys/         # 公共密钥页
│   │   └── error/              # 错误页
│   ├── router/index.js         # 路由配置
│   ├── store/                  # 状态管理
│   ├── utils/                  # 工具函数
│   └── plugins/                # 插件
├── .env.development            # 开发环境变量
├── .env.production             # 生产环境变量
├── vite.config.js              # Vite 配置
└── package.json                # 依赖配置
```

## 页面访问说明

### 开发环境
访问地址: http://localhost:5173

### 路由映射

| 路径 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录页 | 用户登录 |
| `/register` | 注册页 | 用户注册 |
| `/index` | 首页 | 系统概览 |
| `/generate/keygenerate/index` | 密钥生成 | 生成新密钥 |
| `/generate/history/index` | 生成历史 | 查看密钥生成历史 |
| `/generate/commonparam/index` | 公共参数 | 查看/获取公共参数 |
| `/userKeys` | 我的密钥 | 用户密钥列表 |
| `/publickeys` | 公共密钥 | 公共密钥列表 |

### API 前缀

所有 API 请求使用 `/generate-api` 前缀:

```
VITE_APP_BASE_API = '/generate-api'
```

开发环境代理将 `/generate-api` 转发到 `http://localhost:80`

## 启动和构建

### 安装依赖
```bash
cd kms-generate/front
npm install
```

### 开发模式启动
```bash
npm run dev
```

### 生产环境构建
```bash
npm run build:prod
```

### 预览构建结果
```bash
npm run preview
```

## 主要功能

1. **密钥生成** - 支持 SM2、SSCL、AES、RSA、ECC 等多种加密算法
2. **生成历史** - 查看历史生成的密钥记录
3. **公共参数** - 获取系统公共加密参数
4. **用户密钥管理** - 用户查看自己的密钥列表
5. **公共密钥** - 查看公共密钥（需相应权限）

## 技术栈

- Vue 3.4
- Vite 5.3
- Vue Router 4.4
- Pinia 2.1
- Element Plus 2.7
- Axios 0.28
