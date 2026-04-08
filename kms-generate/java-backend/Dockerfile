FROM maven:3.8.8-eclipse-temurin-8 AS build
WORKDIR /build

COPY pom.xml ./
COPY src ./src
COPY config-fisco.toml ./config-fisco.toml

RUN mvn -B -DskipTests package

FROM eclipse-temurin:8-jre
WORKDIR /app

COPY --from=build /build/target/kms-generate.jar /app/kms-generate.jar
COPY --from=build /build/config-fisco.toml /app/config-fisco.toml

EXPOSE 9081

ENTRYPOINT ["java", "-jar", "/app/kms-generate.jar"]
