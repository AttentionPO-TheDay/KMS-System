FROM maven:3.8.8-eclipse-temurin-8 AS build
WORKDIR /build

COPY . ./

RUN mvn -B -DskipTests -pl ruoyi-admin -am package

FROM eclipse-temurin:8-jre
WORKDIR /app

COPY --from=build /build/ruoyi-admin/target/kms-distribute.jar /app/kms-distribute.jar

EXPOSE 8083

ENTRYPOINT ["java", "-jar", "/app/kms-distribute.jar"]
