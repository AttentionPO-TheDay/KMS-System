#!/bin/bash
# 欧拉系统自动适配脚本
# 用于快速部署Falcon-KDS2系统到欧拉系统

set -e

echo "=========================================="
echo "Falcon-KDS2 欧拉系统自动适配脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查系统
check_system() {
    echo -e "${YELLOW}[1/6] 检查系统环境...${NC}"
    
    if [ ! -f /etc/os-release ]; then
        echo -e "${RED}错误: 无法识别系统${NC}"
        exit 1
    fi
    
    OS_NAME=$(grep "^NAME=" /etc/os-release | cut -d'"' -f2)
    echo -e "${GREEN}✓ 系统: $OS_NAME${NC}"
    
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓ Python版本: $PYTHON_VERSION${NC}"
    
    ARCH=$(uname -m)
    echo -e "${GREEN}✓ CPU架构: $ARCH${NC}"
}

# 安装系统依赖
install_dependencies() {
    echo -e "${YELLOW}[2/6] 安装系统依赖...${NC}"
    
    sudo yum update -y > /dev/null 2>&1
    
    PACKAGES=(
        "gcc" "g++" "make"
        "python3-devel" "python3-pip"
        "mysql-devel" "postgresql-devel"
        "libjpeg-turbo-devel" "libpng-devel"
        "openssl-devel" "libevent-devel"
        "git" "wget" "curl"
    )
    
    for pkg in "${PACKAGES[@]}"; do
        if ! rpm -q "$pkg" > /dev/null 2>&1; then
            echo "  安装 $pkg..."
            sudo yum install -y "$pkg" > /dev/null 2>&1
        fi
    done
    
    echo -e "${GREEN}✓ 系统依赖安装完成${NC}"
}

# 升级Python工具
upgrade_python_tools() {
    echo -e "${YELLOW}[3/6] 升级Python工具...${NC}"
    
    python3 -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1
    
    echo -e "${GREEN}✓ Python工具升级完成${NC}"
}

# 安装项目依赖
install_project_deps() {
    echo -e "${YELLOW}[4/6] 安装项目依赖...${NC}"
    
    if [ ! -f "backend/requirements.txt" ]; then
        echo -e "${RED}错误: 找不到requirements.txt${NC}"
        exit 1
    fi
    
    cd backend
    pip install -r requirements.txt > /dev/null 2>&1
    cd ..
    
    echo -e "${GREEN}✓ 项目依赖安装完成${NC}"
}

# 配置环境
configure_environment() {
    echo -e "${YELLOW}[5/6] 配置环境...${NC}"
    
    if [ ! -f "backend/conf/env.py" ]; then
        cp backend/conf/env.example.py backend/conf/env.py
        echo -e "${GREEN}✓ 环境配置文件已创建${NC}"
    fi
    
    # 设置环境变量
    export OMP_NUM_THREADS=1
    export OPENBLAS_NUM_THREADS=1
    
    echo -e "${GREEN}✓ 环境配置完成${NC}"
}

# 初始化数据库
init_database() {
    echo -e "${YELLOW}[6/6] 初始化数据库...${NC}"
    
    cd backend
    python manage.py migrate > /dev/null 2>&1
    cd ..
    
    echo -e "${GREEN}✓ 数据库初始化完成${NC}"
}

# 显示完成信息
show_completion() {
    echo ""
    echo -e "${GREEN}=========================================="
    echo "✓ 欧拉系统适配完成！"
    echo "==========================================${NC}"
    echo ""
    echo "后续步骤:"
    echo "1. 配置数据库连接: nano backend/conf/env.py"
    echo "2. 创建超级用户: cd backend && python manage.py createsuperuser"
    echo "3. 启动开发服务: cd backend && python manage.py runserver 0.0.0.0:8000"
    echo "4. 启动生产服务: cd backend && gunicorn -c gunicorn_conf.py application.wsgi:application"
    echo ""
}

# 主程序
main() {
    check_system
    install_dependencies
    upgrade_python_tools
    install_project_deps
    configure_environment
    init_database
    show_completion
}

main

