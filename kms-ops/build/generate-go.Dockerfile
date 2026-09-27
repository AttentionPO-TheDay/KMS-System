# ---------------------------------------------------------------------------
# kms-generate-go —— 高吞吐入站层（Go / Fiber）
# ---------------------------------------------------------------------------
# 自包含镜像：二进制由 kms-ops/build-local.ps1 交叉编译为 linux/amd64 后打入镜像，
# 运行期不再依赖宿主机挂载。构建上下文为 kms-ops/。
#
# 注意：本项目刻意不在镜像内编译（build-local 已产出静态二进制），
# 因此这里不引入 Go 工具链，镜像更小、构建更快，也避免受 Go/sonic 版本兼容问题影响。
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim

# ca-certificates: 访问 HTTPS 与 FISCO 证书校验需要
# tzdata:          保证容器内时区为 Asia/Shanghai（日志与链上时间戳一致）
# curl:            供健康检查使用
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8

WORKDIR /app

COPY runtime/generate-go/kms-generate-service /app/kms-generate-service
RUN chmod +x /app/kms-generate-service

EXPOSE 8081

# 以非 root 运行（二进制无特权需求）
RUN useradd -r -u 10001 -s /usr/sbin/nologin kms \
    && chown -R kms:kms /app
USER kms

CMD ["/app/kms-generate-service"]
