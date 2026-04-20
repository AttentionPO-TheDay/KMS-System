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

if [ ! -f "$HOME/.cloudflared/f8bf52ad-d8d7-4b80-bb7e-972efe259877.json" ]; then
    echo "[ERROR] local tunnel credentials not found"
    echo "[INFO] expected ~/.cloudflared/f8bf52ad-d8d7-4b80-bb7e-972efe259877.json"
    exit 1
fi

if ! curl -fsS --max-time 5 http://localhost/ping >/dev/null; then
    echo "[ERROR] main compose nginx is not responding on http://localhost/ping"
    echo "[INFO] start kms-ops first, then rerun this script"
    exit 1
fi

echo "[INFO] starting public tunnel..."
run_compose up -d

echo ""
echo "[INFO] tunnel status:"
run_compose ps

echo ""
echo "[INFO] logs: docker compose logs -f cloudflared"
echo "[INFO] domain: https://kms.sinrotic233.com"
