#!/bin/bash

# ================= 配置区域 =================
# 项目根目录 (取决于你在哪里执行命令)
PROJECT_ROOT=$(pwd)

# 路径配置
FISCO_DIR="$PROJECT_ROOT/fisco"
NODE_PATH="$FISCO_DIR/nodes/127.0.0.1"
CONSOLE_DIR="$FISCO_DIR/console"

# Java 配置
JAVA_BACKEND_ROOT="$PROJECT_ROOT/kms-java-backend"
JAVA_CERT_TARGET="$JAVA_BACKEND_ROOT/conf"
JAVA_SRC_TARGET="$FISCO_DIR/contracts/compiled"
JAVA_PACKAGE_NAME="com.ruoyi.keymanage.contracts"

# 合约源码
CONTRACTS_SOL_DIR="$FISCO_DIR/contracts"

# 脚本下载源 
SCRIPT_URL_BUILD="https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh"

echo "=== 开始初始化 (Host模式) ==="
echo "根目录: $PROJECT_ROOT"

# ================= 1. 环境检查 (Java 8) =================
if ! command -v java &> /dev/null; then
    echo "未检测到 Java，正在自动安装..."
    apt-get update && apt-get install -y openjdk-8-jdk
    
    if ! command -v java &> /dev/null; then
        echo "Java 安装失败，请手动安装 openjdk-8-jdk"
        exit 1
    fi
    echo "Java 安装完成"
fi

# ================= 2. 检查 Console =================
if [ ! -d "$CONSOLE_DIR" ]; then
    echo "错误: 未找到 $CONSOLE_DIR"
    exit 1
fi
chmod +x $CONSOLE_DIR/*.sh 2>/dev/null

# ================= 3. 构建节点 =================
mkdir -p $FISCO_DIR && cd $FISCO_DIR

# 下载脚本
if [ ! -f "build_chain.sh" ]; then
    curl -#Lfo build_chain.sh $SCRIPT_URL_BUILD
    chmod u+x build_chain.sh
fi

# 执行构建
if [ ! -d "$NODE_PATH" ]; then
    echo "正在构建节点..."
    # 脚本会自动下载 fisco-bcos 二进制
    ./build_chain.sh -l "127.0.0.1:4" -p 30300,20200,8545
    
    # 修改监听 IP
    sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' $NODE_PATH/node*/config.ini
else
    echo "节点已存在，跳过构建"
fi

# ================= 4. 分发证书 =================
if [ ! -d "$NODE_PATH/sdk" ]; then
    echo "错误: 节点生成失败，未找到 sdk 目录"
    exit 1
fi

mkdir -p $CONSOLE_DIR/conf
cp -f $NODE_PATH/sdk/* $CONSOLE_DIR/conf/

mkdir -p $JAVA_CERT_TARGET
cp -f $NODE_PATH/sdk/* $JAVA_CERT_TARGET/
echo "证书分发完成"

# ================= 5. 编译合约 =================
echo "正在编译合约..."
SOL2JAVA_SCRIPT="$CONSOLE_DIR/sol2java.sh"
SOL_FILES=$(ls $CONTRACTS_SOL_DIR/*.sol 2> /dev/null | wc -l)

if [ "$SOL_FILES" -gt "0" ]; then

    cd $CONSOLE_DIR
    bash sol2java.sh -p $JAVA_PACKAGE_NAME -s $CONTRACTS_SOL_DIR -o $JAVA_SRC_TARGET

    if [ $? -eq 0 ]; then
        echo "Java 代码生成路径: $JAVA_SRC_TARGET"
    else
        echo "编译失败"
    fi
else
    echo "未找到合约文件，跳过编译"
fi

echo "=== 初始化完成 ==="