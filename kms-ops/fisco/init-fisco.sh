#!/bin/bash

# 路径定义
NODE_PATH="/nodes/127.0.0.1"
JAVA_CERT_TARGET="/java-shared-certs"
CONSOLE_DIR="/data/console"

# 1. 构建节点 (仅当配置文件不存在时执行)
if [ ! -f "$NODE_PATH/node0/config.ini" ]; then
    mkdir -p /data && cd /data
    
    # 下载并授权脚本
    curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh
    chmod u+x build_chain.sh
    
    # 构建节点 (-l 0.0.0.0:4 确保外部可连)
    # 注意：构建完成后，所有证书和配置文件都已生成在磁盘上，无需启动
    ./build_chain.sh -l "127.0.0.1:4" -p 30300,20200,8545

    echo "🔧 正在将所有监听 IP 修正为 0.0.0.0..."
    sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' $NODE_PATH/node*/config.ini
fi

# 2. 分发证书给 Java
mkdir -p $JAVA_CERT_TARGET
if [ -d "$NODE_PATH/sdk" ]; then
    cp -f $NODE_PATH/sdk/* $JAVA_CERT_TARGET/
fi

# 3. 分发证书给 Console
echo "📂 正在分发证书给 Console..."
if [ -d "$CONSOLE_DIR/conf" ]; then
    cp -f $NODE_PATH/sdk/* $CONSOLE_DIR/conf/
else
    echo "⚠️ 未找到 Console 目录，跳过分发"
fi