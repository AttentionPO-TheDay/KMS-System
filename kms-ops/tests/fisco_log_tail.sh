#!/bin/bash
# 读链节点日志尾部并挑出可疑行。
# 用文件而不是内联字符串：内联时 PowerShell 会把 $(...) 和重定向吃掉，
# 上一条命令就因此报了个 "C:\dev\null" 的路径错误、根本没执行。
LOG_DIR=${1:-/data/node0/log}

f=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)
if [ -z "$f" ]; then
    echo "($LOG_DIR 下没有日志)"
    exit 0
fi

echo "文件: $f  ($(wc -l < "$f") 行)"
echo
echo "=== 尾部 20 行 ==="
tail -20 "$f"
echo
echo "=== 错误/警告 计数 ==="
grep -c -iE '\|error\||\|warning\||ERROR|WARN' "$f" 2>/dev/null | xargs echo "  匹配行数:"
echo
echo "=== 前 5 条 error/warning ==="
grep -iE '\|error\||\|warning\|' "$f" 2>/dev/null | head -5