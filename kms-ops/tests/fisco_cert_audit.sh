#!/bin/bash
# 证书谱系体检：把"链的 CA"、"节点的证书"、"SDK 用的证书"三者的签发关系一次列清。
#
# 为什么需要它：KMS 连链失败时现象只有一句 ssl handshake failed，
# 而工作区里同时存在 4~5 套 ca.crt（多次 build_chain 留下的）。
# 不把它们摊开比对，就只能在"网络不通/链不出块/证书不对"之间瞎猜。
B=/mnt/c/Users/AllenR/Desktop/kms-code/kms-ops

show() {
    local f="$1" label="$2"
    if [ ! -f "$f" ]; then
        echo "  $label: (缺失)"
        return
    fi
    local subj iss fp
    subj=$(openssl x509 -in "$f" -noout -subject 2>/dev/null | sed 's/subject= *//')
    iss=$(openssl x509 -in "$f" -noout -issuer 2>/dev/null | sed 's/issuer= *//')
    fp=$(openssl x509 -in "$f" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//' | cut -c1-16)
    printf "  %-32s fp=%s\n" "$label" "$fp"
    printf "  %-32s subj=%s\n" "" "$subj"
    printf "  %-32s iss =%s\n" "" "$iss"
}

echo "########## 1. 当前 4 节点链（真正在跑的那套） ##########"
for n in 0 1 2 3; do
    show "$B/nodes/127.0.0.1/node$n/conf/ca.crt" "node$n/conf/ca.crt"
    show "$B/nodes/127.0.0.1/node$n/conf/node.crt" "node$n/conf/node.crt"
done
echo
echo "########## 2. nodes/127.0.0.1/sdk ##########"
show "$B/nodes/127.0.0.1/sdk/ca.crt" "sdk/ca.crt"
show "$B/nodes/127.0.0.1/sdk/sdk.crt" "sdk/sdk.crt"
echo
echo "########## 3. fisco/console/conf（Java 后端打进镜像的那份） ##########"
show "$B/fisco/console/conf/ca.crt" "console/ca.crt"
show "$B/fisco/console/conf/sdk.crt" "console/sdk.crt"
echo
echo "########## 4. kms-java-backend/conf ##########"
show "$B/kms-java-backend/conf/ca.crt" "kms-java-backend/ca.crt"
show "$B/kms-java-backend/conf/sdk.crt" "kms-java-backend/sdk.crt"
echo
echo "########## 5. 备份的单节点链 ##########"
show "$B/nodes/127.0.0.1.bak.20260924094748/node0/conf/ca.crt" "bak/node0/ca.crt"
show "$B/nodes/127.0.0.1.bak.20260924094748/node0/conf/node.crt" "bak/node0/node.crt"
if [ -d "$B/nodes/127.0.0.1.bak.20260924094748/sdk" ]; then
    show "$B/nodes/127.0.0.1.bak.20260924094748/sdk/ca.crt" "bak/sdk/ca.crt"
    show "$B/nodes/127.0.0.1.bak.20260924094748/sdk/sdk.crt" "bak/sdk/sdk.crt"
fi
echo
echo "########## 6. 签发关系校验（链 CA 是否信任各 SDK 证书） ##########"
CHAIN_CA="$B/nodes/127.0.0.1/node0/conf/ca.crt"
for crt in \
    "$B/nodes/127.0.0.1/node0/conf/node.crt|node0 自身 node.crt" \
    "$B/nodes/127.0.0.1/sdk/sdk.crt|nodes/sdk/sdk.crt" \
    "$B/fisco/console/conf/sdk.crt|console/sdk.crt" \
    "$B/kms-java-backend/conf/sdk.crt|kms-java-backend/sdk.crt"
do
    f="${crt%%|*}"; name="${crt##*|}"
    if [ ! -f "$f" ]; then echo "  [--]   $name 不存在"; continue; fi
    if openssl verify -CAfile "$CHAIN_CA" "$f" >/dev/null 2>&1; then
        echo "  [OK]   $name 由当前链 CA 签发"
    else
        echo "  [FAIL] $name 不被当前链 CA 信任  <-- SDK 会 ssl handshake failed"
    fi
done
