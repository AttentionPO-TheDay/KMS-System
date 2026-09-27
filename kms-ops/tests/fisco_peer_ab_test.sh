#!/bin/bash
# 对照实验：把 node0 的 config.ini 换回改写前的版本（peer=127.0.0.1），
# 再启动一次，看是否仍然崩溃。
#
# 目的：区分"崩溃由服务名 peer 引起"与"崩溃与 peer 无关（环境/二进制/状态问题）"。
# 两者的修法完全不同，猜错会白折腾很久。
set -u
cd /data/node0 || exit 1

echo "当前 peer:"
grep -E '^\s*node\.[0-9]=' config.ini | sed 's/^/  /'

if [ -f config.ini.orig ]; then
    cp config.ini /tmp/config.ini.servicename
    cp config.ini.orig config.ini
    echo
    echo "已换回原始 config.ini（peer=127.0.0.1，备份在 /tmp/config.ini.servicename）"
    grep -E '^\s*node\.[0-9]=' config.ini | sed 's/^/  /'
else
    echo "没有 config.ini.orig，无法做对照"
fi