#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DOCKER_COMPOSE=()

init_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(docker compose)
        return 0
    fi

    if sudo -n docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(sudo docker compose)
        return 0
    fi

    echo "[ERROR] docker compose is not available or requires sudo without cached credentials"
    exit 1
}

run_compose() {
    if [ ${#DOCKER_COMPOSE[@]} -eq 0 ]; then
        init_docker_compose
    fi
    "${DOCKER_COMPOSE[@]}" "$@"
}

echo "[INFO] stopping public tunnel..."
run_compose down
