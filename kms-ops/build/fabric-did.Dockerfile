# 独立 Java 8 JVM，避免 SDK singleton/BGM provider 改动现有 FISCO 进程。
# 链方建议 Zulu 8u302+；此镜像的实际国密 TLS 兼容性仍需授权实链验证。
FROM azul/zulu-openjdk:8-jre
WORKDIR /run/fabric-did/work
COPY runtime/fabric-did/app.jar /app/app.jar
# 必须保留签名过的 provider 及全部运行依赖；禁止只复制 thin 主 JAR。
COPY runtime/fabric-did/lib/ /app/lib/
RUN mkdir -p /run/fabric-did/work
EXPOSE 9094
ENTRYPOINT ["java", "-DfabricSDK.configuration=/run/fabric-did/gm-sdk.properties", "-jar", "/app/app.jar"]
