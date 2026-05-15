#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$SCRIPT_DIR/runtime"
FRONT_ROOT="$SCRIPT_DIR/front"
DOCKER_CMD=()

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Missing command: $1" >&2
    return 1
  fi
}

init_docker_cmd() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi

  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
    return 0
  fi

  if sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
    return 0
  fi

  echo "[ERROR] Docker is installed but not accessible. Re-run this script with sudo, for example: sudo ./kms-ops/build-local.sh" >&2
  exit 1
}

run_docker() {
  if [ ${#DOCKER_CMD[@]} -eq 0 ]; then
    init_docker_cmd
  fi
  "${DOCKER_CMD[@]}" "$@"
}

new_clean_directory() {
  rm -rf "$1"
  mkdir -p "$1"
}

copy_artifact() {
  local source="$1"
  local destination="$2"

  if [ ! -e "$source" ]; then
    echo "[ERROR] Build artifact not found: $source" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$destination")"
  rm -rf "$destination"
  cp -R "$source" "$destination"
}

invoke_maven_build() {
  local project_dir="$1"
  local unwritable_target=""

  if find "$project_dir" -type d -name target ! -writable -print -quit | grep -q .; then
    unwritable_target=1
  fi

  echo "Building Maven project: $project_dir"
  if command -v mvn >/dev/null 2>&1 && [ -z "$unwritable_target" ]; then
    (cd "$project_dir" && mvn -DskipTests package)
  else
    require_cmd docker
    run_docker run --rm \
      -v "$project_dir:/build" \
      -w /build \
      maven:3.8.8-eclipse-temurin-8 \
      mvn -DskipTests package
  fi
}

invoke_maven_build_with_args() {
  local project_dir="$1"
  local unwritable_target=""
  shift

  if find "$project_dir" -type d -name target ! -writable -print -quit | grep -q .; then
    unwritable_target=1
  fi

  echo "Building Maven project: $project_dir"
  if command -v mvn >/dev/null 2>&1 && [ -z "$unwritable_target" ]; then
    (cd "$project_dir" && mvn "$@")
  else
    require_cmd docker
    run_docker run --rm \
      -v "$project_dir:/build" \
      -w /build \
      maven:3.8.8-eclipse-temurin-8 \
      mvn "$@"
  fi
}

invoke_frontend_build() {
  local project_dir="$1"
  local build_script="$2"

  echo "Building frontend project: $project_dir"
  if command -v npm >/dev/null 2>&1; then
    (
      cd "$project_dir"
      if [ -f package-lock.json ]; then
        npm ci
      else
        npm install
      fi
      npm run "$build_script"
    )
  else
    require_cmd docker
    run_docker run --rm \
      -v "$project_dir:/app" \
      -w /app \
      node:20-bookworm \
      bash -lc "if [ -f package-lock.json ]; then npm ci; else npm install; fi && npm run $build_script"
  fi
}

invoke_go_project_build() {
  local project_dir="$1"
  local output_name="$2"

  mkdir -p "$project_dir/dist"
  echo "Building Go project: $project_dir"

  if command -v go >/dev/null 2>&1; then
    (
      cd "$project_dir"
      GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o "dist/$output_name" .
    )
  else
    require_cmd docker
    run_docker run --rm \
      -e GOOS=linux \
      -e GOARCH=amd64 \
      -e CGO_ENABLED=0 \
      -e GOPROXY=https://goproxy.cn,direct \
      -v "$project_dir:/src" \
      -w /src \
      golang:1.25.5 \
      go build -o "dist/$output_name" .
  fi
}

invoke_go_linux_build() {
  local project_dir="$1"
  local output_name="$2"

  mkdir -p "$project_dir/dist"
  echo "Building Go project for Linux: $project_dir"

  if command -v go >/dev/null 2>&1; then
    (
      cd "$project_dir"
      GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o "dist/$output_name" ./cmd/main.go
    )
  else
    require_cmd docker
    run_docker run --rm \
      -e GOOS=linux \
      -e GOARCH=amd64 \
      -e CGO_ENABLED=0 \
      -e GOPROXY=https://goproxy.cn,direct \
      -v "$project_dir:/src" \
      -w /src \
      golang:1.25.5 \
      go build -o "dist/$output_name" ./cmd/main.go
  fi
}

generate_java_dir="$REPO_ROOT/kms-generate/java-backend"
updatedel_java_dir="$REPO_ROOT/kms-updatedel/java-backend"
distribute_java_dir="$REPO_ROOT/kms-distribute/java-backend"
generate_go_dir="$REPO_ROOT/kms-generate/go-backend"
updatedel_go_dir="$REPO_ROOT/kms-updatedel/go-backend"
acceptance_go_dir="$REPO_ROOT/kms-acceptance/backend"
generate_front_dir="$REPO_ROOT/kms-generate/front"
updatedel_front_dir="$REPO_ROOT/kms-updatedel/front"
distribute_front_dir="$REPO_ROOT/kms-distribute/extracted/ruoyi (2)/web"
user_front_dir="$REPO_ROOT/kms-user/front"
acceptance_front_dir="$REPO_ROOT/kms-acceptance/front"
acceptance_security_dir="$REPO_ROOT/security"

new_clean_directory "$RUNTIME_ROOT"
new_clean_directory "$FRONT_ROOT/generate"
new_clean_directory "$FRONT_ROOT/updatedel"
new_clean_directory "$FRONT_ROOT/distribute"
new_clean_directory "$FRONT_ROOT/user"
new_clean_directory "$FRONT_ROOT/acceptance"

invoke_maven_build "$generate_java_dir"
invoke_maven_build_with_args "$updatedel_java_dir" -pl ruoyi-admin -am -DskipTests package
invoke_maven_build_with_args "$distribute_java_dir" -B -DskipTests -pl ruoyi-admin -am clean package

invoke_go_linux_build "$generate_go_dir" "kms-generate-service"
invoke_go_linux_build "$updatedel_go_dir" "kms-updatedel-service"
invoke_go_project_build "$acceptance_go_dir" "kms-acceptance-backend"

invoke_frontend_build "$generate_front_dir" "build:prod"
invoke_frontend_build "$updatedel_front_dir" "build:prod"
invoke_frontend_build "$distribute_front_dir" "build"
invoke_frontend_build "$user_front_dir" "build"
invoke_frontend_build "$acceptance_front_dir" "build"

copy_artifact "$generate_java_dir/ruoyi-admin/target/kms-generate.jar" "$RUNTIME_ROOT/generate-java/kms-generate.jar"
copy_artifact "$generate_java_dir/config-fisco.toml" "$RUNTIME_ROOT/generate-java/config-fisco.toml"
copy_artifact "$updatedel_java_dir/ruoyi-admin/target/kms-updatedel.jar" "$RUNTIME_ROOT/updatedel-java/kms-updatedel.jar"
copy_artifact "$updatedel_java_dir/ruoyi-admin/src/main/resources/config-fisco.toml" "$RUNTIME_ROOT/updatedel-java/config-fisco.toml"
copy_artifact "$distribute_java_dir/ruoyi-admin/target/kms-distribute.jar" "$RUNTIME_ROOT/distribute-java/kms-distribute.jar"

copy_artifact "$generate_go_dir/dist/kms-generate-service" "$RUNTIME_ROOT/generate-go/kms-generate-service"
copy_artifact "$updatedel_go_dir/dist/kms-updatedel-service" "$RUNTIME_ROOT/updatedel-go/kms-updatedel-service"
copy_artifact "$acceptance_go_dir/dist/kms-acceptance-backend" "$RUNTIME_ROOT/acceptance-go/kms-acceptance-backend"
copy_artifact "$acceptance_security_dir/security_test.sh" "$RUNTIME_ROOT/acceptance-go/security/security_test.sh"

copy_artifact "$generate_front_dir/dist/." "$FRONT_ROOT/generate"
copy_artifact "$updatedel_front_dir/dist/." "$FRONT_ROOT/updatedel"
copy_artifact "$distribute_front_dir/dist/." "$FRONT_ROOT/distribute"
copy_artifact "$user_front_dir/dist/." "$FRONT_ROOT/user"
copy_artifact "$acceptance_front_dir/dist/." "$FRONT_ROOT/acceptance"

echo "Local build artifacts are ready under kms-ops/runtime and kms-ops/front."
echo "Run 'docker compose up -d' in kms-ops/."
