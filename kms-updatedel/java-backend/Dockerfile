FROM maven:3.8.8-eclipse-temurin-8 AS build
WORKDIR /build

COPY pom.xml ./
COPY src ./src

RUN mvn -B -DskipTests package

FROM eclipse-temurin:8-jre
WORKDIR /app

COPY --from=build /build/target/kms-updatedel.jar /app/kms-updatedel.jar

EXPOSE 9082

ENTRYPOINT ["java", "-jar", "/app/kms-updatedel.jar"]
