# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /workspace
ARG MAVEN_PROFILE=local

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.m2 \
    chmod +x mvnw \
    && ./mvnw -B -P${MAVEN_PROFILE} -DskipTests package

FROM eclipse-temurin:17-jre-jammy AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system spring \
    && useradd --system --gid spring --home-dir /app spring

WORKDIR /app
COPY --from=build --chown=spring:spring /workspace/target/prjspringboothive-ver1.0.jar app.jar
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app/data \
    && chown -R spring:spring /app/data

EXPOSE 9900

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["java", "-jar", "/app/app.jar"]
