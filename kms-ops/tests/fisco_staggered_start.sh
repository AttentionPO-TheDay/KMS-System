#!/bin/bash
# 错开启动 4 个节点，验证"冷启动视图跑飞"这一假设。
#
# 为什么怀疑它：4 个节点由同一个循环在同一瞬间拉起，每个节点在还没和对端建立
# P2P 会话时就开始计时提议 → 超时 → 换视图；等别人也起来时，各自视图号已经差开了，
# 于是 Prepare 消息因视图不匹配被丢弃。日志里 addRawPrepare 有 172 次、
# onPrepare/onCommit 却是 0，正是这个形态。
set -u

echo "=== 停掉所有节点 ==="
pkill -f fisco-bcos
sleep 3
ps aux | grep -c "[f]isco-bcos" | xargs echo "  剩余进程:"

echo
echo "=== 错开启动（每个间隔 6 秒）==="
for n in 0 1 2 3; do
    cd "/data/node$n" || exit 1
    rm -f nohup.out
    nohup /data/fisco-bcos -c config.ini >> nohup.out 2>&1 &
    echo "  已启动 node$n (pid=$!)"
    sleep 6
done

echo
echo "=== 等 25 秒让共识收敛 ==="
sleep 25

echo "=== node0 共识阶段统计 ==="
f=$(ls -t /data/node0/log/*.log 2>/dev/null | head -1)
echo "  日志: $f"
for k in addRawPrepare onPrepare onCommit commitBlock; do
    printf "    %-16s %s\n" "$k" "$(grep -cE "$k" "$f" 2>/dev/null)"
done
echo
echo "=== node0 最近 6 行 ==="
tail -6 "$f"