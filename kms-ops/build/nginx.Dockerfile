# ---------------------------------------------------------------------------
# kms-gateway —— 统一网关（Nginx：静态资源 + API 反向代理）
# ---------------------------------------------------------------------------
# 自包含镜像：nginx.conf、门户落地页与 4 个前端产物全部打入镜像。
# 原实现把这些目录逐个 bind mount 进来（共 8 条），镜像化后不再依赖宿主机。
# ---------------------------------------------------------------------------
FROM nginx:alpine

ENV TZ=Asia/Shanghai

# 时区与排查用工具（wget 由 busybox 提供，健康检查够用）
RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

# 主配置（覆盖镜像自带 default.conf 之外的主配置）
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# 可复用配置片段：安全响应头、SPA 入口禁缓存
# （nginx 的 add_header 不继承，这些片段必须在每个自带 add_header 的
#   location 里再 include 一次，见 nginx.conf 注释）
COPY nginx/snippets/ /etc/nginx/snippets/
COPY nginx/demo-server.conf.template /etc/nginx/kms-demo.template
COPY nginx/30-kms-demo.sh /docker-entrypoint.d/30-kms-demo.sh
RUN chmod +x /docker-entrypoint.d/30-kms-demo.sh \
    && printf '%s\n' 'server { listen 8088; server_name _; return 404; }' > /etc/nginx/kms-demo.conf

# 静态资源：门户 + 2 个前端
# （/generate/ 与 /distribute/ 两个静态前端均已退役：前者页面并入统一管理端，
#   后者随 2026-09-26 代码清理下线，网关对两者均显式返回 404。
#   两者的**后端**路由不受影响：/generate-api/ 与 /pqkds-api/ 仍在服务）
#
# /user/ 于阶段 1（前端合并）下线：kms-user 的业务页整体迁入 kms-updatedel，
# 跨应用跳转同步删除，网关对 /user/ 显式返回 404。应用目录保留至阶段 9，
# 但已不再构建，因此这里**不再 COPY** —— 继续 COPY 会因产物缺失而构建失败。
COPY portal/ /usr/share/nginx/html/
COPY front/updatedel/   /usr/share/nginx/html/updatedel/
COPY front/acceptance/  /usr/share/nginx/html/acceptance/

# 清理镜像自带的示例页，避免 / 被默认页覆盖
RUN rm -f /usr/share/nginx/html/index.nginx-debian.html 2>/dev/null || true

EXPOSE 80

# 校验配置语法；配置有误会在此直接失败，而不是等到启动
RUN nginx -t

CMD ["nginx", "-g", "daemon off;"]
