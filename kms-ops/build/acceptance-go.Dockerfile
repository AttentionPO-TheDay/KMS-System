# ---------------------------------------------------------------------------
# kms-acceptance-backend —— 验收与压测后端（Go）
# ---------------------------------------------------------------------------
# 自包含镜像。三个要点：
#   1. security/ 目录必须打入镜像：验收台的「安全演练」会直接执行其中的
#      security_test.sh（原实现靠 bind mount 提供）。
#   2. 依赖（bash/curl/jq/wrk）在**构建期**安装。原实现是在容器启动命令里
#      `apt-get install`，这会使容器启动依赖外网、且每次重建结果不确定。
#   3. wrk 是压测必需项，缺失时验收台的 TPS 压测不可用。
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates tzdata bash curl jq wrk \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
# wrk 的绝对路径，供后端调用（原 compose 中即为此值）
ENV WRK_PATH=/usr/bin/wrk

WORKDIR /app

COPY runtime/acceptance-go/kms-acceptance-backend /app/kms-acceptance-backend
COPY runtime/acceptance-go/security/ /app/security/
RUN chmod +x /app/kms-acceptance-backend \
    && find /app/security -name '*.sh' -exec chmod +x {} \;

EXPOSE 9090

RUN useradd -r -u 10001 -s /usr/sbin/nologin kms \
    && chown -R kms:kms /app
USER kms

CMD ["/app/kms-acceptance-backend"]
