#!/bin/bash
# 把各节点 config.ini 里的 peer 地址从 127.0.0.1 改写成**容器服务名**。
#
# 为什么需要改写：`build_chain.sh` 默认按单机同网络命名空间生成，peer 写的是
# `127.0.0.1:3030N`。一旦拆成"每节点一个容器"，各容器有自己的网络命名空间，
# 127.0.0.1 就只指向自己了 —— 节点之间实际连不上，共识自然起不来。
#
# 官方 docker 模式（`-d`）靠 `--network=host` 回避了这个问题，
# 但 Docker Desktop for Windows 不支持 host 网络模式，所以这里改走
# 「桥接网络 + 服务名解析」：把 peer 写成 `fisco-nodeN:3030N`。
set -eu

BASE=/data
changed=0

for n in 0 1 2 3; do
    cfg="$BASE/node$n/config.ini"
    [ -f "$cfg" ] || { echo "  跳过 node$n（无 config.ini）"; continue; }

    cp "$cfg" "$cfg.orig"

    # node.K=127.0.0.1:3030K  ->  node.K=fisco-nodeK:3030K
    for k in 0 1 2 3; do
        sed -i "s|node\.$k=127\.0\.0\.1:3030$k|node.$k=fisco-node$k:3030$k|" "$cfg"
    done

    # listen_ip 保持 0.0.0.0，容器内需要监听所有接口
    echo "  node$n peer 现在为:"
    grep -E '^\s*node\.[0-9]=' "$cfg" | sed 's/^/    /'
    changed=$((changed + 1))
done

echo
echo "已改写 $changed 个节点。原文件备份为 config.ini.orig"
echo
echo "=== 校验：是否还残留 127.0.0.1 的 peer ==="
if grep -lE '^\s*node\.[0-9]+=127\.0\.0\.1' /data/node*/config.ini 2>/dev/null; then
    echo "  ^ 仍有残留，需检查"
else
    echo "  无残留"
fi
