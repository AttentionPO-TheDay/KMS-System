# 已退役：`/generate/` 前端

> 一句话结论：本目录（`kms-generate/front`）**已停止构建、也不再对外提供**。
> 代码保留在仓库里仅供查阅；`generate` 只保留**后端**。

## 一、退役事实

1. 本前端已随本次结构收敛**退役**，依据 `doc/kms-restructure-plan.md` §7 P5 第 6 项。
2. 页面与能力早已并入统一管理端 `kms-updatedel`
   （仓库内 `kms-updatedel/front/src.bak-premerge/` 就是当时合并留下的痕迹），
   两者高度重复，故不再作为独立前端交付：前端交付物由 **5 端收敛为 4 端**。
3. 网关侧：`kms-ops/nginx/nginx.conf` 已移除原来的 `location /generate/`，
   现在访问 `http://127.0.0.1/generate/` 由网关**显式返回 404**
   （不能让它回落到默认 location —— 那里 `try_files` 会返回 200 的门户首页，
   等于用 HTML 冒充"还活着"）。
4. 构建侧：`kms-ops/build-local.ps1` 与 `kms-ops/build-local.sh` 都不再构建本目录、
   不再向 `kms-ops/front` 投放产物；`kms-ops/build/nginx.Dockerfile` 不再 `COPY front/generate/`。
5. 启动侧：`kms-ops/start.sh` 不再创建 `front/generate`，也不再把它列为启动前置产物
   （原先缺 `front/generate/index.html` 会直接 `exit 1`）。
6. 校验侧：`kms-ops/check.ps1` 已删除 `/generate/` 返回 200 的断言；
   `tools/smoke-frontends.mjs` 与 `tools/verify-admin-pages.mjs` 已去掉 generate 这一端。

## 二、仍然活着的东西（不要顺手删掉）

1. `/generate-api/*` 网关路由：**保留**，仍代理到 `generate-java:9081`。
2. `generate-java` / `generate-go` 两个服务：**保留**，仍在 `docker-compose.yml` 与构建脚本里。
3. 原因：统一管理端 `/updatedel/` 仍在通过 `/generate-api/...` 调用
   **公钥查询 / 用户密钥池 / 生成历史**等接口。本次下线的只是**静态前端**，不是 generate 后端。

## 三、不要在没有决策的情况下把它加回来

本目录仍受版本控制，但重新启用它属于**产品决策**，不是顺手恢复的一行配置：

1. 需要同时改回的地方：`nginx.conf` 的 `location /generate/` 与静态资源正则、
   `build-local.ps1` 的前端构建与产物投放、`build/nginx.Dockerfile` 的 `COPY`、
   `check.ps1`、`tools/smoke-frontends.mjs`、`tools/verify-admin-pages.mjs`。
2. 更要先回答：统一管理端已经吸收了它的页面，重新分叉出第二份管理端界面会立刻开始漂移
   —— 这正是当初把它合并掉的原因。
