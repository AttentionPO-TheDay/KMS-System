#!/bin/bash
# KMS-OPS 一键停止脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  KMS-OPS 双系统停止脚本"
echo "=========================================="

# 检查 docker-compose 是否存在
if [ ! -f "docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found!"
    exit 1
fi

# 停止所有容器
echo "[INFO] 停止所有容器..."
docker-compose down

echo ""
echo "[INFO] 容器状态:"
docker-compose ps

echo ""
echo "=========================================="
echo "  KMS-OPS 停止完成!"
echo "  (数据保留在本地目录)"
echo "=========================================="
