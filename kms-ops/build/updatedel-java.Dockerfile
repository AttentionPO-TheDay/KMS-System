# ---------------------------------------------------------------------------
# kms-updatedel-java —— 业务层（RuoYi / Spring Boot）
# ---------------------------------------------------------------------------
# 与 generate-java 同构：jar + FISCO 配置 + SDK 证书三者缺一不可。
# ---------------------------------------------------------------------------
FROM eclipse-temurin:8-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
# 同 generate-java：java.io.tmpdir 必须对运行用户可写，
# 否则 Webank 原生加密库无法解压 .so，SM2/SSCL 相关功能全部失败。
ENV JAVA_OPTS="-Xms256m -Xmx512m -Duser.timezone=Asia/Shanghai -Djava.io.tmpdir=/app/tmp -Duser.home=/app"

WORKDIR /app

COPY runtime/updatedel-java/kms-updatedel.jar /app/kms-updatedel.jar
COPY runtime/updatedel-java/config-fisco.toml /app/config-fisco.toml
COPY fisco/console/conf/ /app/conf/

EXPOSE 9082

RUN useradd -r -u 10001 -s /usr/sbin/nologin kms \
    && mkdir -p /app/logs /app/tmp /app/.fisco/nativeutils \
    && chown -R kms:kms /app \
    && chmod 755 /app
USER kms

CMD ["sh", "-c", "exec java $JAVA_OPTS -jar /app/kms-updatedel.jar"]