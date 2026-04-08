#!/bin/bash

SOL2JAVA_SCRIPT="/dist/console/sol2java.sh"
SOL_DIR="/dist/contracts/solidity"
OUTPUT_BASE_DIR="/dist/contracts/compiled"

echo "正在使用本地挂载的 Console 工具编译合约..."

# 给所有 sh 脚本加执行权限 (防止 Windows 丢失权限)
chmod +x /dist/console/*.sh

# 检查工具
if [ ! -f "$SOL2JAVA_SCRIPT" ]; then
    echo "❌ 错误：找不到 $SOL2JAVA_SCRIPT"
    exit 1
fi

# 准备目录
mkdir -p $OUTPUT_BASE_DIR
cd $OUTPUT_BASE_DIR

# 执行编译
bash $SOL2JAVA_SCRIPT -p com.temp.pkg -s $SOL_DIR

echo "✅ 编译脚本执行完毕！"
tail -f /dev/null