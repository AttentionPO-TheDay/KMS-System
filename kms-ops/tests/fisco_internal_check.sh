#!/bin/bash
# 节点内部自检：进程是否还在、端口是否在听、RPC 是否应答。
# 用来区分"节点进程没了" / "端口没听" / "只是宿主转发不通"。
echo "=== 进程 ==="
ps aux | grep "[f]isco-bcos" | awk '{print "  pid="$2" "$11" "$12}' || true
echo "  (以上为空即进程不在)"

echo
echo "=== RPC 端口监听 ==="
for p in 8545 8546 8547 8548; do
    if (echo > /dev/tcp/127.0.0.1/$p) >/dev/null 2>&1; then echo "  :$p 可连"; else echo "  :$p 不可连"; fi
done

echo
echo "=== 本机 HTTP RPC 直连（不依赖宿主转发）==="
if command -v curl >/dev/null 2>&1; then
    curl -s -m 8 -X POST -H 'Content-Type: application/json' \
      --data '{"jsonrpc":"2.0","id":1,"method":"getBlockNumber","params":[1]}' \
      http://127.0.0.1:8545 || echo "  (curl 无输出)"
else
    echo "  (容器内无 curl，跳过)"
fi

echo
echo "=== 节点日志尾部 ==="
f=$(ls -t /data/node0/log/*.log 2>/dev/null | head -1)
echo "  文件: $f"
tail -6 "$f" 2>/dev/null