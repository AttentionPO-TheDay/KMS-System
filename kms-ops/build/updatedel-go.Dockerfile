# ---------------------------------------------------------------------------
# kms-updatedel-go —— 高吞吐入站层（Go / Fiber）
# ---------------------------------------------------------------------------
# 与 generate-go 结构相同；二进制由 build-local 交叉编译后打入镜像。
# 注意：该服务依赖 sonic v1.15.1（v1.14.2 与较新 Go 工具链不兼容），
# 因而不在镜像内编译，直接使用已验证的二进制。
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8

WORKDIR /app

COPY runtime/updatedel-go/kms-updatedel-service /app/kms-updatedel-service
RUN chmod +x /app/kms-updatedel-service

EXPOSE 8082

RUN useradd -r -u 10001 -s /usr/sbin/nologin kms \
    && chown -R kms:kms /app
USER kms

CMD ["/app/kms-updatedel-service"]
