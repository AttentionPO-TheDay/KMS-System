#!/bin/bash
# 追一轮 PBFT 的完整阶段，定位究竟卡在哪一步。
# PBFT 正常顺序：addRawPrepare → onPrepare/onPreCommit → onCommit → commitBlock/生成区块。
# 如果只有 addRawPrepare 而没有后续阶段，说明其它节点根本没收到/没接受这个提议。
f=$(ls -t /data/node0/log/*.log 2>/dev/null | head -1)
echo "文件: $f"
echo
echo "=== 各 PBFT 阶段出现的次数 ==="
for k in addRawPrepare onPrepare onPreCommit onCommit commitBlock broadcastPrepare \
         onViewChange reachViewChange onRecvProposal 'PBFT.*Prepare' 'PBFT.*Commit'; do
    printf "  %-20s %s\n" "$k" "$(grep -cE "$k" "$f" 2>/dev/null)"
done
echo
echo "=== 是否出现过 blockNumber 递增 / 区块提交 ==="
grep -cE 'commitBlock|BlockChain.*commit|number=1' "$f" 2>/dev/null | xargs echo "  区块相关行数:"
echo
echo "=== 最近 12 行（看它停在哪一步）==="
tail -12 "$f"