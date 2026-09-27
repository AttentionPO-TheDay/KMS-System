#!/bin/bash
# 新链体检：确认这次 build 出来的 CA / 节点 / SDK 三方是**同一条 PKI**。
#
# 上一轮的教训：链能起来、peer 也能连，但 SDK 的证书来自另一次 build，
# 于是所有客户端都在 TLS 握手阶段被拒 —— 而现象看起来只是"KMS 写不了链"。
# 所以"链活着"不等于"链可用"，这一条必须在换链前先验。
OUT="${1:-/tmp/fisco-rebuild/out}"

echo "OUT=$OUT"
echo
echo "########## 1. 四个 nodeid 是否互不相同、且都在创世里 ##########"
for n in 0 1 2 3; do
    id=$(cat "$OUT/127.0.0.1/node$n/conf/node.nodeid")
    ing=$(grep -c "$id" "$OUT/127.0.0.1/node0/conf/group.1.genesis")
    printf "  node%s nodeid=%s... 在创世=%s\n" "$n" "$(echo "$id" | cut -c1-16)" "$ing"
done
echo -n "  去重后 nodeid 数 = "
for n in 0 1 2 3; do cat "$OUT/127.0.0.1/node$n/conf/node.nodeid"; echo; done | sort -u | wc -l

echo
echo "########## 2. 创世是否四节点共用（hash 一致） ##########"
for n in 0 1 2 3; do
    printf "  node%s: %s\n" "$n" "$(sha256sum "$OUT/127.0.0.1/node$n/conf/group.1.genesis" | cut -c1-16)"
done

echo
echo "########## 3. 证书签发关系 ##########"
check() {
    local ca="$1" crt="$2" name="$3"
    if openssl verify -CAfile "$ca" "$crt" >/dev/null 2>&1; then
        echo "  [OK]   $name"
    else
        echo "  [FAIL] $name   <-- 会握手失败"
    fi
}
SDK_CA="$OUT/127.0.0.1/sdk/ca.crt"
check "$SDK_CA" "$OUT/127.0.0.1/sdk/sdk.crt" "SDK 证书 <- sdk/ca.crt"
for n in 0 1 2 3; do
    CHCA="$OUT/127.0.0.1/node$n/conf/channel_cert/ca.crt"
    check "$CHCA" "$OUT/127.0.0.1/sdk/sdk.crt" "SDK 证书 <- node$n 的 channel CA（握手真正看这条）"
    check "$CHCA" "$OUT/127.0.0.1/node$n/conf/channel_cert/node.crt" "node$n channel 证书 <- 自己的 channel CA"
done
check "$OUT/cert/agency/agency.crt" "$OUT/127.0.0.1/node0/conf/node.crt" "node0 身份证书 <- agency CA"

echo
echo "########## 4. 关键证书指纹与主体 ##########"
for f in cert/ca.crt cert/agency/agency.crt cert/agency/channel/ca.crt \
         127.0.0.1/node0/conf/ca.crt 127.0.0.1/node0/conf/channel_cert/ca.crt \
         127.0.0.1/sdk/ca.crt 127.0.0.1/sdk/sdk.crt; do
    subj=$(openssl x509 -in "$OUT/$f" -noout -subject 2>/dev/null | sed 's/subject= *//')
    fp=$(openssl x509 -in "$OUT/$f" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//' | cut -c1-17)
    printf "  %-42s %s\n" "$f" "$fp"
    printf "  %-42s %s\n" "" "$subj"
done

echo
echo "########## 5. 结论速查 ##########"
echo "  sdk/ca.crt 与各节点 channel_cert/ca.crt 是否同一份（决定 SDK 能否连）："
for n in 0 1 2 3; do
    a=$(sha256sum "$SDK_CA" | cut -d' ' -f1)
    b=$(sha256sum "$OUT/127.0.0.1/node$n/conf/channel_cert/ca.crt" | cut -d' ' -f1)
    [ "$a" = "$b" ] && echo "    node$n: 同一份" || echo "    node$n: **不同**"
done
