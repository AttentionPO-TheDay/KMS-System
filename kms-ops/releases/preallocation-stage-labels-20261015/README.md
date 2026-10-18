# 预分配成功页步骤名称发布

范围：仅更新 `updatedel` 前端的预分配执行流程标题，顺序为“并行抽样短向量”“离线生成格陷门”“快速委派格基向量”。业务处理函数与后端未更改。

基线：服务器原网关镜像 `sha256:f375f66364f241393a5d280e6a46b8dcd3d54cbb6f7590644a3c3f41229f0d3b`。为避免带入工作区其他改动，以该镜像已有静态资源为基线，只覆盖改字及引用链涉及的 98 个文件，并保留旧文件以兼容已打开的页面。

发布：`bash /home/rbf/kms-sys/releases/preallocation-stage-labels-20261015/apply.sh`。脚本核对包摘要和基线镜像，重建并切换 Nginx 网关；失败时自动恢复原镜像。回滚镜像标签为 `kms-gateway-nginx:before-preallocation-stage-labels-20261015`。

结果：已部署。线上 `/updatedel/demo` 和目标 JS 的 SHA256 与发布包一致；线上 98 个新入口所需文件逐一返回 HTTP 200 且摘要一致；三个标题各出现一次；Nginx 配置检查通过，六个受检后端和数据库容器 ID 与启动时间未变。
