#!/bin/bash
# KMS-OPS 一键启动脚本
# 支持 kms-generate 和 kms-updatedel 双系统启动

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  KMS-OPS 双系统启动脚本"
echo "=========================================="

# 检查 docker-compose 是否存在
if [ ! -f "docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found!"
    exit 1
fi

# 创建必要的目录
echo "[INFO] 创建必要的数据目录..."
mkdir -p mysql/data mysql/init redis/data kafka/kafka_data
mkdir -p fisco/nodes/127.0.0.1
mkdir -p nginx/logs
mkdir -p front/generate front/updatedel
mkdir -p kms-generate/go-backend kms-generate/java-backend
mkdir -p kms-updatedel/go-backend kms-updatedel/java-backend

# 启动所有容器
echo "[INFO] 启动所有容器..."
docker-compose up -d

# 等待中间件就绪
echo "[INFO] 等待中间件启动..."
sleep 5

# 检查容器状态
echo ""
echo "[INFO] 容器状态:"
docker-compose ps

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
echo "  - generate-java:  8080"
echo "  - updatedel-go:   8082"
echo "  - updatedel-java: 8083"
echo ""
echo "  中间件端口:"
echo "  - MySQL: 3306"
echo "  - Redis: 6379"
echo "  - Kafka: 9092"
echo "=========================================="
