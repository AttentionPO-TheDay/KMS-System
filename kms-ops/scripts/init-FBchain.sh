#!/bin/bash

set -e

PROJECT_ROOT=$(pwd)
KMS_OPS_DIR="$PROJECT_ROOT/kms-ops"
FISCO_DIR="$KMS_OPS_DIR/fisco"
LIVE_NODE_PATH="$KMS_OPS_DIR/nodes/127.0.0.1"
CONSOLE_DIR="$FISCO_DIR/console"
JAVA_BACKEND_ROOT="$KMS_OPS_DIR/kms-java-backend"
JAVA_CERT_TARGET="$JAVA_BACKEND_ROOT/conf"
JAVA_SRC_TARGET="$FISCO_DIR/contracts/compiled"
JAVA_PACKAGE_NAME="com.ruoyi.keymanage.contracts"
CONTRACTS_SOL_DIR="$FISCO_DIR/contracts"
SCRIPT_URL_BUILD="https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh"
REFRESH_TEMPLATE_SCRIPT="$KMS_OPS_DIR/scripts/refresh-fisco-template.sh"

echo "=== 开始单节点链手动初始化（兜底模式） ==="
echo "根目录: $PROJECT_ROOT"

echo "[INFO] 正常启动请使用 kms-ops/start.sh；本脚本仅用于从零重建单节点模板。"

if ! command -v java &> /dev/null; then
    echo "未检测到 Java，正在自动安装..."
    apt-get update && apt-get install -y openjdk-8-jdk
    if ! command -v java &> /dev/null; then
        echo "Java 安装失败，请手动安装 openjdk-8-jdk"
        exit 1
    fi
fi

if [ ! -d "$CONSOLE_DIR" ]; then
    echo "错误: 未找到 $CONSOLE_DIR"
    exit 1
fi
chmod +x "$CONSOLE_DIR"/*.sh 2>/dev/null || true

mkdir -p "$FISCO_DIR"
cd "$FISCO_DIR"

if [ ! -f "build_chain.sh" ]; then
    curl -#Lfo build_chain.sh "$SCRIPT_URL_BUILD"
    chmod u+x build_chain.sh
fi

if [ ! -d "$LIVE_NODE_PATH" ]; then
    echo "[INFO] 正在从零构建单节点链..."
    ./build_chain.sh -l "127.0.0.1:1" -p 30300,20200,8545
    cp -R "$PROJECT_ROOT/nodes/127.0.0.1" "$LIVE_NODE_PATH"
    sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' "$LIVE_NODE_PATH"/node*/config.ini
else
    echo "[INFO] 单节点链已存在，跳过构建"
fi

if [ ! -d "$LIVE_NODE_PATH/sdk" ]; then
    echo "错误: 节点生成失败，未找到 sdk 目录"
    exit 1
fi

mkdir -p "$CONSOLE_DIR/conf"
cp -f "$LIVE_NODE_PATH"/sdk/* "$CONSOLE_DIR/conf/"

mkdir -p "$JAVA_CERT_TARGET"
cp -f "$LIVE_NODE_PATH"/sdk/* "$JAVA_CERT_TARGET/"
echo "[INFO] 证书分发完成"

echo "[INFO] 正在编译合约 Java 包装..."
SOL_FILES=$(ls "$CONTRACTS_SOL_DIR"/*.sol 2> /dev/null | wc -l)
if [ "$SOL_FILES" -gt "0" ]; then
    cd "$CONSOLE_DIR"
    bash sol2java.sh -p "$JAVA_PACKAGE_NAME" -s "$CONTRACTS_SOL_DIR" -o "$JAVA_SRC_TARGET"
fi

if [ -x "$REFRESH_TEMPLATE_SCRIPT" ]; then
    bash "$REFRESH_TEMPLATE_SCRIPT"
fi

echo "=== 单节点链手动初始化完成 ==="
