# ---------------------------------------------------------------------------
# kms-generate-java —— 业务层（RuoYi / Spring Boot）
# ---------------------------------------------------------------------------
# 自包含镜像。除 jar 外必须打入两类「隐形依赖」，否则链上功能不可用：
#   1. config-fisco.toml  → FISCO Java SDK 的连接配置（peers 指向 fisco-node:20200）
#   2. fisco/console/conf → ca.crt / sdk.crt / sdk.key，SDK 建链时的 TLS 证书
# 此前这两项靠宿主机 bind mount 提供，镜像化后必须在构建期复制进来。
# ---------------------------------------------------------------------------
FROM eclipse-temurin:8-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
# 固定时区，避免链上时间戳因容器默认 UTC 而与业务时间不一致。
# -Djava.io.tmpdir 必须指向运行用户可写的目录：
#   Webank 原生加密库（com.webank.wedpr.NativeUtils）在运行时会把 .so
#   解压到临时目录，若不可写会抛 "user dir unavailable / Failed to load library"，
#   导致 SM2/SSCL 密钥生成全部失败（原生库不可用时无软件回退）。
ENV JAVA_OPTS="-Xms256m -Xmx512m -Duser.timezone=Asia/Shanghai -Djava.io.tmpdir=/app/tmp -Duser.home=/app"

WORKDIR /app

COPY runtime/generate-java/kms-generate.jar /app/kms-generate.jar
COPY runtime/generate-java/config-fisco.toml /app/config-fisco.toml
# SDK 证书目录：Java 侧按 classpath:conf / /app/conf 读取
COPY fisco/console/conf/ /app/conf/

EXPOSE 9081

# 非 root 运行；/app 与其下 tmp/logs 必须对运行用户可写（原生库解压与日志）
RUN useradd -r -u 10001 -s /usr/sbin/nologin kms \
    && mkdir -p /app/logs /app/tmp /app/.fisco/nativeutils \
    && chown -R kms:kms /app \
    && chmod 755 /app
USER kms

# JAVA_OPTS 交由 shell 展开，因此用 sh -c 形式启动
CMD ["sh", "-c", "exec java $JAVA_OPTS -jar /app/kms-generate.jar"]
