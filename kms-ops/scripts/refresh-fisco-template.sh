#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KMS_OPS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LIVE_NODE_DIR="$KMS_OPS_DIR/nodes/127.0.0.1"
LIVE_CONSOLE_CONF_DIR="$KMS_OPS_DIR/fisco/console/conf"
LIVE_STATE_FILE="$KMS_OPS_DIR/fisco/live/contract.env"
TEMPLATE_ROOT="$KMS_OPS_DIR/fisco/template"
TEMPLATE_NODE_DIR="$TEMPLATE_ROOT/nodes/127.0.0.1"
TEMPLATE_CONSOLE_CONF_DIR="$TEMPLATE_ROOT/console/conf"
TEMPLATE_STATE_FILE="$TEMPLATE_ROOT/state/.env.template.local"

require_path() {
  local path="$1"
  local label="$2"
  if [ ! -e "$path" ]; then
    echo "[ERROR] 缺少${label}: $path" >&2
    exit 1
  fi
}

copy_dir() {
  local src="$1"
  local dst="$2"
  rm -rf "$dst"
  mkdir -p "$dst"
  cp -a "$src/." "$dst/"
}

prune_template_runtime_noise() {
  local node_root="$1"

  rm -f "$node_root"/node0/nohup.out
  rm -rf "$node_root"/node0/log
  rm -rf "$node_root"/console
}

require_path "$LIVE_NODE_DIR/node0/start.sh" "单节点 live 链"
require_path "$LIVE_CONSOLE_CONF_DIR/ca.crt" "FISCO console 证书"
require_path "$LIVE_CONSOLE_CONF_DIR/sdk.crt" "FISCO console SDK 证书"
require_path "$LIVE_CONSOLE_CONF_DIR/sdk.key" "FISCO console SDK 私钥"

mkdir -p "$TEMPLATE_ROOT/state"
copy_dir "$LIVE_NODE_DIR" "$TEMPLATE_NODE_DIR"
prune_template_runtime_noise "$TEMPLATE_NODE_DIR"
copy_dir "$LIVE_CONSOLE_CONF_DIR" "$TEMPLATE_CONSOLE_CONF_DIR"

if [ -f "$LIVE_STATE_FILE" ]; then
  cp "$LIVE_STATE_FILE" "$TEMPLATE_STATE_FILE"
fi

echo "[INFO] 单节点 FISCO 模板已刷新到: $TEMPLATE_ROOT"
