#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
MYSQL_DATA_DIR="$SCRIPT_DIR/mysql/data"
REDIS_DATA_DIR="$SCRIPT_DIR/redis/data"
KAFKA_DATA_DIR="$SCRIPT_DIR/kafka/kafka_data"
FISCO_LIVE_NODE_DIR="$SCRIPT_DIR/nodes"
FISCO_LIVE_STATE_DIR="$SCRIPT_DIR/fisco/live"
DOCKER_CMD=()
DOCKER_COMPOSE=()

init_docker_cmd() {
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
    return 0
  fi

  if sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
    return 0
  fi

  echo "[ERROR] Docker is not accessible. Re-run with sudo or make sure current user can access Docker." >&2
  exit 1
}

run_docker() {
  if [ ${#DOCKER_CMD[@]} -eq 0 ]; then
    init_docker_cmd
  fi
  "${DOCKER_CMD[@]}" "$@"
}

init_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE=(docker compose)
    return 0
  fi

  if sudo -n docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE=(sudo docker compose)
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE=(docker-compose)
    return 0
  fi

  echo "[ERROR] docker compose is not available." >&2
  exit 1
}

run_compose() {
  if [ ${#DOCKER_COMPOSE[@]} -eq 0 ]; then
    init_docker_compose
  fi
  "${DOCKER_COMPOSE[@]}" -f "$COMPOSE_FILE" "$@"
}

clear_dir_with_helper() {
  local target="$1"
  mkdir -p "$target"
  run_docker run --rm \
    -e HOST_UID="$(id -u)" \
    -e HOST_GID="$(id -g)" \
    -v "$target:/target" \
    alpine sh -lc 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true && chown "$HOST_UID:$HOST_GID" /target'
}

echo "=========================================="
echo "  KMS-OPS 环境重建脚本"
echo "=========================================="

echo "[INFO] 停止当前容器..."
run_compose down || true

echo "[INFO] 清理 MySQL / Redis / Kafka 运行数据..."
clear_dir_with_helper "$MYSQL_DATA_DIR"
clear_dir_with_helper "$REDIS_DATA_DIR"
clear_dir_with_helper "$KAFKA_DATA_DIR"

echo "[INFO] 清理 FISCO live 运行态，后续将从模板恢复..."
clear_dir_with_helper "$FISCO_LIVE_NODE_DIR"
clear_dir_with_helper "$FISCO_LIVE_STATE_DIR"

echo "[INFO] 重新构建本地产物..."
bash "$SCRIPT_DIR/build-local.sh"

echo "[INFO] 从模板恢复并重新启动环境..."
bash "$SCRIPT_DIR/start.sh"

echo "[INFO] 环境重建完成。"
