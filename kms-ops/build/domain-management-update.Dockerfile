# 复用已发布生命周期镜像的运行环境，仅替换本次 Java 应用。
FROM kms-updatedel-java:local
COPY --chown=kms:kms runtime/updatedel-java/kms-updatedel.jar /app/kms-updatedel.jar
