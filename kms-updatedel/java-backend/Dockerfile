FROM maven:3.8.8-eclipse-temurin-8 AS build
WORKDIR /build

COPY pom.xml ./
COPY ruoyi-admin ./ruoyi-admin
COPY ruoyi-common ./ruoyi-common
COPY ruoyi-framework ./ruoyi-framework
COPY ruoyi-system ./ruoyi-system
COPY ruoyi-quartz ./ruoyi-quartz
COPY ruoyi-generator ./ruoyi-generator

RUN mvn -B -pl ruoyi-admin -am -DskipTests package

FROM eclipse-temurin:8-jre
WORKDIR /app

COPY --from=build /build/ruoyi-admin/target/kms-updatedel.jar /app/kms-updatedel.jar
COPY --from=build /build/ruoyi-admin/src/main/resources/config-fisco.toml /app/config-fisco.toml

EXPOSE 9082

ENTRYPOINT ["java", "-jar", "/app/kms-updatedel.jar"]
