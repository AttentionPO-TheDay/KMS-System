#!/bin/bash

set -euo pipefail

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

    if command -v run_compose >/dev/null 2>&1; then
        DOCKER_COMPOSE=(run_compose)
        return 0
    fi

    if sudo -n run_compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(sudo run_compose)
        return 0
    fi

    echo "[ERROR] docker compose is not available or requires sudo without cached credentials" >&2
    exit 1
}

run_compose() {
    if [ ${#DOCKER_COMPOSE[@]} -eq 0 ]; then
        init_docker_compose
    fi
    "${DOCKER_COMPOSE[@]}" "$@"
}

ENV_FILE="$SCRIPT_DIR/.env"
LIVE_STATE_DIR="$SCRIPT_DIR/fisco/live"
LIVE_STATE_FILE="$LIVE_STATE_DIR/contract.env"
CONSOLE_SERVICE="fisco-console"
CONSOLE_WORKDIR="/app"

log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

require_file() {
    if [ ! -f "$1" ]; then
        log_error "Missing file: $1"
        exit 1
    fi
}

set_env_value() {
    local file="$1"
    local key="$2"
    local value="$3"
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$file"
    fi
}

extract_latest_address() {
    run_compose exec -T "$CONSOLE_SERVICE" bash -lc "if [ -f /tmp/keyevidence-deploy.log ]; then cat /tmp/keyevidence-deploy.log; fi; if [ -f $CONSOLE_WORKDIR/deploylog.txt ]; then grep 'KeyEvidence' $CONSOLE_WORKDIR/deploylog.txt | tail -n 1; fi" | sed -n 's/.*\(0x[a-fA-F0-9]\{40\}\).*/\1/p' | tail -n 1
}

extract_private_key_hex() {
    run_compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && pem_file=\$(ls -t account/*.pem account/ecdsa/*.pem accounts/*.pem 2>/dev/null | head -n 1); if [ -z \"\$pem_file\" ]; then exit 1; fi; openssl ec -in \"\$pem_file\" -text -noout 2>/dev/null | sed -n '3,5p' | tr -d ': \\n'"
}

wait_console_ready() {
    local retries=20
    while [ "$retries" -gt 0 ]; do
        if run_compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && test -f console.sh" >/dev/null 2>&1; then
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    return 1
}

require_file "$ENV_FILE"
require_file "$SCRIPT_DIR/docker-compose.yml"
mkdir -p "$LIVE_STATE_DIR"

log_info "Ensuring FISCO node and console are running"
# ⚠️ 服务名是 `fisco-node0`（另有 node1..3），**不是** `fisco-node`。
# 这个脚本是在单节点时代写的，链改多节点后调用会直接报
# "no such service: fisco-node" 并中止 —— 而它中止的位置在编译之前，
# 所以现象是"脚本跑不起来"，而不是"合约版本旧"，不容易联想到服务改名。
# fisco-console 通过 network_mode: service:fisco-node0 共享 node0 的网络栈，
# 因此拉起 console 本身就会带上 node0（compose 的 depends_on 语义）。
run_compose up -d "$CONSOLE_SERVICE"

if ! wait_console_ready; then
    log_error "FISCO console is not ready"
    exit 1
fi

log_info "Compiling KeyEvidence contract in console"
run_compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && chmod +x *.sh && bash ./sol2java.sh -p com.temp.pkg -s contracts/solidity >/tmp/keyevidence-compile.log 2>&1 || { cat /tmp/keyevidence-compile.log; exit 1; }"

log_info "Deploying KeyEvidence contract"
run_compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && chmod +x *.sh && ./console.sh deploy KeyEvidence >/tmp/keyevidence-deploy.log 2>&1 || { cat /tmp/keyevidence-deploy.log; exit 1; }"

CONTRACT_ADDRESS="$(extract_latest_address)"
if [ -z "$CONTRACT_ADDRESS" ]; then
    log_error "Failed to extract deployed contract address"
    exit 1
fi

PRIVATE_KEY_HEX="$(extract_private_key_hex || true)"
if [ -z "$PRIVATE_KEY_HEX" ]; then
    log_error "Failed to extract console account private key"
    exit 1
fi

set_env_value "$ENV_FILE" "FISCO_CONTRACT_ADDRESS" "$CONTRACT_ADDRESS"
set_env_value "$ENV_FILE" "FISCO_PRIVATE_KEY" "$PRIVATE_KEY_HEX"
set_env_value "$ENV_FILE" "KMS_CHAIN_RESULT_TOPIC" "key_chain_result"
set_env_value "$LIVE_STATE_FILE" "FISCO_CONTRACT_ADDRESS" "$CONTRACT_ADDRESS"
set_env_value "$LIVE_STATE_FILE" "FISCO_PRIVATE_KEY" "$PRIVATE_KEY_HEX"
set_env_value "$LIVE_STATE_FILE" "KMS_CHAIN_RESULT_TOPIC" "key_chain_result"

log_info "Updated local chain state with contract address: $CONTRACT_ADDRESS"

# 同步合约状态到模板，确保 rebuild-env / start.sh 恢复时携带私钥
TEMPLATE_STATE_DIR="$SCRIPT_DIR/fisco/template/state"
TEMPLATE_STATE_FILE="$TEMPLATE_STATE_DIR/.env.template.local"
if [ -f "$TEMPLATE_STATE_FILE" ]; then
    log_info "Syncing contract state back to template..."
    set_env_value "$TEMPLATE_STATE_FILE" "FISCO_CONTRACT_ADDRESS" "$CONTRACT_ADDRESS"
    set_env_value "$TEMPLATE_STATE_FILE" "FISCO_PRIVATE_KEY" "$PRIVATE_KEY_HEX"
    set_env_value "$TEMPLATE_STATE_FILE" "KMS_CHAIN_RESULT_TOPIC" "key_chain_result"
fi

log_info "Recreating Java services with unified blockchain config"
run_compose up -d --force-recreate generate-java updatedel-java

log_info "KeyEvidence deployed successfully"
log_info "FISCO_CONTRACT_ADDRESS=$CONTRACT_ADDRESS"
