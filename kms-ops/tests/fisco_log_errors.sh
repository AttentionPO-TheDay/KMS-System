#!/bin/bash
# 按 FISCO 的日志格式（`级别|时间|模块|内容`）挑出 error/warning 行。
# 注意级别在**行首**：上一条我写成 `\|error\|`（要求前面有竖线），方向反了，
# 于是"计数 19"却"一条都打不出来" —— 这种自相矛盾的输出本身就是排查线索。
LOG_DIR=${1:-/data/node0/log}
f=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)
[ -z "$f" ] && { echo "(无日志)"; exit 0; }

echo "文件: $f"
echo
echo "=== 行首为 error 的行 ==="
grep -E '^error\|' "$f" | tail -12
echo "  (共 $(grep -cE '^error\|' "$f") 条)"
echo
echo "=== 行首为 warning 的行（去重统计）==="
grep -E '^warning\|' "$f" | sed -E 's/^warning\|[0-9: .-]+\|//' | sort | uniq -c | sort -rn | head -8
echo
echo "=== 启动阶段（前 40 行）里的关键信息 ==="
head -40 "$f" | grep -iE 'group|sealer|consensus|genesis|node' | head -12
echo
echo "=== 最近的共识活动（最后 6 条 SEALER/CONSENSUS）==="
grep -E '\[CONSENSUS\]|\[SEALER\]' "$f" | tail -6