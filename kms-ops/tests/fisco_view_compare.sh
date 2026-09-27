#!/bin/bash
# 对比 node0 与 node1 的共识视角，并检查证书材料是否齐全/一致。
# 目的：区分"leader 没提议" 与 "follower 收不到消息"——两者的修法完全不同。
echo "=== 各节点 conf 下的证书材料 ==="
for n in 0 1 2 3; do
    printf "  node%s: " "$n"
    for f in ca.crt node.crt node.key node.nodeid; do
        if [ -f "/data/node$n/conf/$f" ]; then printf "%s=有 " "$f"; else printf "%s=**缺** " "$f"; fi
    done
    echo
done

echo
echo "=== ca.crt 是否 4 节点一致（应完全一致）==="
for n in 0 1 2 3; do
    h=$(sha256sum "/data/node$n/conf/ca.crt" 2>/dev/null | cut -c1-16)
    echo "  node$n ca.crt = $h"
done

echo
echo "=== node1 最近共识活动 ==="
f1=$(ls -t /data/node1/log/*.log 2>/dev/null | head -1)
if [ -n "$f1" ]; then
    grep -E '\[CONSENSUS\]|\[SEALER\]|startPeerSession' "$f1" | tail -8
    echo "  --- node1 的 error 行 ---"
    grep -E '^error\|' "$f1" | tail -5
else
    echo "  (node1 无日志)"
fi

echo
echo "=== node0 是否收到来自其他节点的 PBFT 消息 ==="
f0=$(ls -t /data/node0/log/*.log 2>/dev/null | head -1)
grep -cE 'addRawPrepare|onPrepare|PBFT.*Prepare' "$f0" 2>/dev/null | xargs echo "  prepare 相关行数:"
grep -E 'nodeIdx=[1-3]' "$f0" 2>/dev/null | tail -4 | sed 's/^/  /'
echo "  （若上面为空，说明 node0 从未看到其它节点的共识动作）"