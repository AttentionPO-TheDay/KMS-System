#!/bin/bash
# KMS-OPS 一键启动脚本
# 支持 kms-generate 和 kms-updatedel 双系统启动

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

    if command -v run_compose >/dev/null 2>&1; then
        DOCKER_COMPOSE=(run_compose)
        return 0
    fi

    if sudo -n run_compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(sudo run_compose)
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

echo "=========================================="
echo "  KMS-OPS 双系统启动脚本"
echo "=========================================="

# 检查 compose 文件是否存在
if [ ! -f "docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found!"
    exit 1
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] 未检测到 .env，使用 .env.example 初始化..."
        cp .env.example .env
    else
        echo "[ERROR] .env and .env.example are both missing" >&2
        exit 1
    fi
fi

# 创建必要的目录
echo "[INFO] 创建必要的数据目录..."
mkdir -p mysql/data mysql/init redis/data kafka/kafka_data
mkdir -p fisco/console/account fisco/console/accounts fisco/console/log
mkdir -p nginx/logs
mkdir -p front/generate front/updatedel front/distribute front/user front/acceptance
mkdir -p runtime/generate-go runtime/generate-java runtime/updatedel-go runtime/updatedel-java runtime/distribute-java runtime/acceptance-go

if [ ! -f "runtime/generate-go/kms-generate-service" ] \
    || [ ! -f "runtime/generate-java/kms-generate.jar" ] \
    || [ ! -f "runtime/updatedel-go/kms-updatedel-service" ] \
    || [ ! -f "runtime/updatedel-java/kms-updatedel.jar" ] \
    || [ ! -f "runtime/distribute-java/kms-distribute.jar" ] \
    || [ ! -f "runtime/acceptance-go/kms-acceptance-backend" ] \
    || [ ! -f "front/generate/index.html" ] \
    || [ ! -f "front/updatedel/index.html" ] \
    || [ ! -f "front/distribute/index.html" ] \
    || [ ! -f "front/user/index.html" ] \
    || [ ! -f "front/acceptance/index.html" ]; then
    echo "[ERROR] 缺少运行产物，请先执行 bash ./build-local.sh" >&2
    exit 1
fi

if [ ! -f "nodes/127.0.0.1/node0/start.sh" ]; then
    echo "[INFO] 未检测到单节点 FISCO 数据，开始生成节点文件..."
    rm -rf nodes
    bash ./fisco/build_chain.sh -l "127.0.0.1:1" -p 30300,20200,8545
    sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' nodes/127.0.0.1/node*/config.ini
fi

if [ ! -d "fisco/console/apps" ] || [ ! -d "fisco/console/lib" ]; then
    echo "[INFO] 未检测到 FISCO Console 运行包，开始下载并初始化..."
    rm -rf nodes/127.0.0.1/console nodes/127.0.0.1/console*.tar.gz
    (
        cd nodes/127.0.0.1
        bash ./download_console.sh -f
    )
    rm -rf fisco/console/apps fisco/console/lib fisco/console/classes
    cp -R nodes/127.0.0.1/console/apps fisco/console/apps
    cp -R nodes/127.0.0.1/console/lib fisco/console/lib
    if [ -d "nodes/127.0.0.1/console/classes" ]; then
        cp -R nodes/127.0.0.1/console/classes fisco/console/classes
    fi
fi

if [ -d "nodes/127.0.0.1/sdk" ]; then
    cp -f nodes/127.0.0.1/sdk/* fisco/console/conf/
fi

if ! chmod -R 0777 kafka/kafka_data 2>/dev/null; then
    echo "[WARN] 无法修改 kafka/kafka_data 权限，继续使用现有权限..."
fi

# 启动所有容器
# build-local.sh 会重建 runtime/front 目录，绑定挂载需要重建容器才能看到新 inode。
echo "[INFO] 启动所有容器..."
run_compose up -d --force-recreate \
    fisco-node \
    fisco-console \
    generate-go \
    generate-java \
    updatedel-go \
    updatedel-java \
    kms-distribute \
    acceptance-backend \
    nginx

# 等待中间件就绪
echo "[INFO] 等待中间件启动..."
sleep 5

if ! grep -q '^FISCO_CONTRACT_ADDRESS=0x' .env; then
    echo "[INFO] 未检测到已部署合约地址，开始自动部署 KeyEvidence..."
    bash ./deploy-keyevidence.sh
fi

# 检查容器状态
echo ""
echo "[INFO] 容器状态:"
run_compose ps

echo ""
echo "=========================================="
echo "  KMS-OPS 启动完成!"
echo ""
echo "  访问地址:"
echo "  - 网关:      http://localhost:80"
echo "  - 生成系统:  http://localhost:80/generate/"
echo "  - 生命周期:  http://localhost:80/lifecycle/"
echo ""
echo "  后端端口:"
echo "  - generate-go:     8081"
echo "  - generate-java:  9081"
echo "  - updatedel-go:   8082"
echo "  - updatedel-java: 9082"
echo ""
echo "  中间件端口:"
echo "  - MySQL: 3306"
echo "  - Redis: 6379"
echo "  - Kafka: 9092"
echo "=========================================="
