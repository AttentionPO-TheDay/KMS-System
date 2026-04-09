#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
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
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

extract_latest_address() {
    docker-compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && grep 'KeyEvidence' deploylog.txt | tail -n 1" | sed -n 's/.*\(0x[a-fA-F0-9]\{40\}\).*/\1/p'
}

extract_private_key_hex() {
    docker-compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && pem_file=\$(ls -t account/*.pem accounts/*.pem 2>/dev/null | head -n 1); if [ -z \"\$pem_file\" ]; then exit 1; fi; openssl ec -in \"\$pem_file\" -text -noout 2>/dev/null | sed -n '3,5p' | tr -d ': \\n'"
}

wait_console_ready() {
    local retries=20
    while [ "$retries" -gt 0 ]; do
        if docker-compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && test -f console.sh" >/dev/null 2>&1; then
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    return 1
}

require_file "$ENV_FILE"
require_file "$SCRIPT_DIR/docker-compose.yml"

log_info "Ensuring FISCO node and console are running"
docker-compose up -d fisco-node "$CONSOLE_SERVICE"

if ! wait_console_ready; then
    log_error "FISCO console is not ready"
    exit 1
fi

log_info "Compiling KeyEvidence contract in console"
docker-compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && chmod +x *.sh && bash ./sol2java.sh -p com.temp.pkg -s contracts/solidity >/tmp/keyevidence-compile.log 2>&1 || { cat /tmp/keyevidence-compile.log; exit 1; }"

log_info "Deploying KeyEvidence contract"
docker-compose exec -T "$CONSOLE_SERVICE" bash -lc "cd $CONSOLE_WORKDIR && chmod +x *.sh && ./console.sh deploy KeyEvidence >/tmp/keyevidence-deploy.log 2>&1 || { cat /tmp/keyevidence-deploy.log; exit 1; }"

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

set_env_value "FISCO_CONTRACT_ADDRESS" "$CONTRACT_ADDRESS"
set_env_value "FISCO_PRIVATE_KEY" "$PRIVATE_KEY_HEX"
set_env_value "KMS_CHAIN_RESULT_TOPIC" "key_chain_result"

log_info "Updated .env with contract address: $CONTRACT_ADDRESS"

log_info "Recreating Java services with unified blockchain config"
docker-compose up -d --force-recreate generate-java updatedel-java kms-distribute

log_info "KeyEvidence deployed successfully"
log_info "FISCO_CONTRACT_ADDRESS=$CONTRACT_ADDRESS"
