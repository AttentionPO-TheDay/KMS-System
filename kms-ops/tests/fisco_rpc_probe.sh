#!/bin/bash
# 用 /dev/tcp 直连本节点 JSON-RPC（容器内无 curl）。
# 用法: bash /data/_rpc_probe.sh [port]
PORT="${1:-8545}"

rpc() {
    local body="$1"
    exec 3<>/dev/tcp/127.0.0.1/$PORT || { echo "  (连不上 127.0.0.1:$PORT)"; return 1; }
    printf 'POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s' "${#body}" "$body" >&3
    cat <&3 | tail -1
    exec 3<&-
}

echo "=== 本节点 nodeid ==="
cat /data/node0/conf/node.nodeid 2>/dev/null | cut -c1-24
echo
echo "=== RPC @$PORT ==="
for m in getBlockNumber getPbftView getSealerList getObserverList getNodeIDList getSyncStatus getPeers; do
    printf '%-18s ' "$m"
    if [ "$m" = "getPeers" ]; then
        rpc "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$m\",\"params\":[]}"
    else
        rpc "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$m\",\"params\":[1]}"
    fi
    echo
done
echo
echo "=== getConsensusStatus ==="
rpc '{"jsonrpc":"2.0","id":1,"method":"getConsensusStatus","params":[1]}'
