#!/bin/bash

set -e

NODE_PATH="/nodes/127.0.0.1"
JAVA_CERT_TARGET="/java-shared-certs"
CONSOLE_DIR="/data/console"
TEMPLATE_NODE_PATH="/data/template/nodes/127.0.0.1"
TEMPLATE_CONSOLE_CONF="/data/template/console/conf"

if [ ! -f "$NODE_PATH/node0/config.ini" ]; then
    if [ -f "$TEMPLATE_NODE_PATH/node0/config.ini" ]; then
        echo "[INFO] 从单节点模板恢复 FISCO 链..."
        mkdir -p /nodes/127.0.0.1
        cp -a "$TEMPLATE_NODE_PATH/." "$NODE_PATH/"
    else
        echo "[INFO] 未发现模板，执行单节点兜底构建..."
        mkdir -p /data && cd /data
        curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh
        chmod u+x build_chain.sh
        ./build_chain.sh -l "127.0.0.1:1" -p 30300,20200,8545
        cp -a /data/nodes/127.0.0.1/. "$NODE_PATH/"
    fi

    echo "[INFO] 正在将监听 IP 修正为 0.0.0.0..."
    sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' "$NODE_PATH"/node*/config.ini
fi

mkdir -p "$JAVA_CERT_TARGET"
if [ -d "$NODE_PATH/sdk" ]; then
    cp -f "$NODE_PATH"/sdk/* "$JAVA_CERT_TARGET/"
fi

echo "[INFO] 正在分发证书给 Console..."
if [ -d "$CONSOLE_DIR/conf" ] && [ -d "$NODE_PATH/sdk" ]; then
    cp -f "$NODE_PATH"/sdk/* "$CONSOLE_DIR/conf/"
elif [ -d "$CONSOLE_DIR/conf" ] && [ -d "$TEMPLATE_CONSOLE_CONF" ]; then
    cp -f "$TEMPLATE_CONSOLE_CONF"/* "$CONSOLE_DIR/conf/"
else
    echo "[WARN] 未找到 Console 目录或模板证书，跳过分发"
fi
