#!/bin/bash
# 链节点自检：端口是否监听、各节点日志尾部。
# 写成文件而不是 docker exec 里的内联字符串 —— 内联时 PowerShell 会吃掉 \$ 转义，
# 结果是脚本没跑、只留下一句语法错误（这个坑我在别处已经踩过一次）。
echo "=== 监听端口（RPC 8545-8548 / channel 20200-20203）==="
for p in 8545 8546 8547 8548 20200 20201 20202 20203; do
    if (echo > /dev/tcp/127.0.0.1/$p) >/dev/null 2>&1; then
        echo "  :$p 可连"
    else
        echo "  :$p 不可连"
    fi
done

echo
echo "=== 各节点 nohup.out 尾部 ==="
for n in 0 1 2 3; do
    echo "--- node$n ---"
    if [ -f "/data/node$n/nohup.out" ]; then
        tail -4 "/data/node$n/nohup.out"
    else
        echo "  (无 nohup.out)"
    fi
done

echo
echo "=== 进程 ==="
ps aux | grep "[f]isco-bcos" | awk '{print "  pid="$2"  "$11" "$12}'