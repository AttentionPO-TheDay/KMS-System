#!/bin/bash
# 对比「创世块里登记的共识节点」与「各节点自己的 nodeid」，并列出关键共识配置。
# 共识卡住时，这两者对不上（或少登记/多登记）是首要排查点。
echo "=== 创世块里的节点/共识相关字段 ==="
grep -nE '"(sealer|observer|nodeList|nodes)"|sealerList|consensus' /data/node0/conf/group.1.genesis | head -20

echo
echo "=== 各节点 nodeid ==="
for n in 0 1 2 3; do
    id=$(cat "/data/node$n/conf/node.nodeid" 2>/dev/null)
    echo "  node$n : ${id:0:24}...  (len=${#id})"
done

echo
echo "=== 创世里出现了几个 nodeid（应与 4 一致）==="
for n in 0 1 2 3; do
    id=$(cat "/data/node$n/conf/node.nodeid" 2>/dev/null)
    if grep -q "$id" /data/node0/conf/group.1.genesis 2>/dev/null; then
        echo "  node$n 的 nodeid 在创世中: 是"
    else
        echo "  node$n 的 nodeid 在创世中: 否  <-- 它不是创世共识节点"
    fi
done

echo
echo "=== group.1.ini（运行时可增删共识节点的地方）==="
cat /data/node0/conf/group.1.ini 2>/dev/null || echo "  (无 group.1.ini)"

echo
echo "=== 各节点 config.ini 的 [consensus] 段 ==="
for n in 0 1 2 3; do
    echo "--- node$n ---"
    awk '/^\[consensus\]/,/^\[/' "/data/node$n/config.ini" 2>/dev/null | head -8
done