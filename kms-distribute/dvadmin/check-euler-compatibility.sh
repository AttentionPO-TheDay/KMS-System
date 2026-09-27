# 欧拉系统兼容性检查脚本
# 用于验证系统是否满足Falcon-KDS2的运行要求

#!/bin/bash

echo "=========================================="
echo "Falcon-KDS2 欧拉系统兼容性检查"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

# 检查函数
check_item() {
    local name=$1
    local command=$2
    local required=$3
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASS++))
    else
        if [ "$required" = "required" ]; then
            echo -e "${RED}✗${NC} $name (必需)"
            ((FAIL++))
        else
            echo -e "${YELLOW}⚠${NC} $name (可选)"
            ((WARN++))
        fi
    fi
}

# 获取版本信息
get_version() {
    local command=$1
    eval "$command" 2>/dev/null | head -1
}

echo -e "${BLUE}=== 系统信息 ===${NC}"
echo "操作系统: $(grep '^NAME=' /etc/os-release | cut -d'"' -f2)"
echo "内核版本: $(uname -r)"
echo "CPU架构: $(uname -m)"
echo "CPU核心数: $(nproc)"
echo ""

echo -e "${BLUE}=== 必需组件检查 ===${NC}"
check_item "Python 3.9+" "python3 --version | grep -E '3\.[9-9]|[4-9]\.[0-9]'" "required"
check_item "pip" "pip3 --version" "required"
check_item "gcc编译器" "gcc --version" "required"
check_item "git版本控制" "git --version" "required"
echo ""

echo -e "${BLUE}=== 数据库驱动检查 ===${NC}"
check_item "MySQL开发库" "rpm -q mysql-devel" "required"
check_item "PostgreSQL开发库" "rpm -q postgresql-devel" "optional"
echo ""

echo -e "${BLUE}=== 图像处理库检查 ===${NC}"
check_item "libjpeg-turbo" "rpm -q libjpeg-turbo-devel" "required"
check_item "libpng" "rpm -q libpng-devel" "required"
echo ""

echo -e "${BLUE}=== 其他依赖检查 ===${NC}"
check_item "OpenSSL开发库" "rpm -q openssl-devel" "required"
check_item "libevent库" "rpm -q libevent-devel" "optional"
check_item "Docker" "docker --version" "optional"
echo ""

echo -e "${BLUE}=== Python包检查 ===${NC}"
check_item "Django" "python3 -c 'import django'" "required"
check_item "numpy" "python3 -c 'import numpy'" "required"
check_item "scipy" "python3 -c 'import scipy'" "required"
check_item "pycryptodome" "python3 -c 'import Crypto'" "required"
check_item "Pillow" "python3 -c 'import PIL'" "required"
echo ""

echo -e "${BLUE}=== 网络连接检查 ===${NC}"
check_item "互联网连接" "ping -c 1 8.8.8.8" "optional"
check_item "PyPI访问" "curl -s https://pypi.org > /dev/null" "optional"
echo ""

echo -e "${BLUE}=== 磁盘空间检查 ===${NC}"
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓${NC} 磁盘空间充足 (使用率: ${DISK_USAGE}%)"
    ((PASS++))
else
    echo -e "${RED}✗${NC} 磁盘空间不足 (使用率: ${DISK_USAGE}%)"
    ((FAIL++))
fi
echo ""

echo -e "${BLUE}=== 内存检查 ===${NC}"
TOTAL_MEM=$(free -h | awk 'NR==2 {print $2}')
AVAILABLE_MEM=$(free -h | awk 'NR==2 {print $7}')
echo "总内存: $TOTAL_MEM"
echo "可用内存: $AVAILABLE_MEM"
echo ""

echo "=========================================="
echo -e "${GREEN}通过: $PASS${NC} | ${YELLOW}警告: $WARN${NC} | ${RED}失败: $FAIL${NC}"
echo "=========================================="
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ 系统满足所有必需要求，可以部署！${NC}"
    exit 0
else
    echo -e "${RED}✗ 系统不满足某些必需要求，请先解决问题。${NC}"
    exit 1
fi

