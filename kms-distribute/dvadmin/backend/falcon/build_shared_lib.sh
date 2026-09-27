#!/usr/bin/env bash
# =============================================================================
# 编译 Falcon 参考实现的共享库
# -----------------------------------------------------------------------------
# 为什么需要：
#   PQKDS 的 Falcon 无证书实现（backend/pqkds/falcon_trapgen_dll.py）通过
#   ctypes 加载 falcon512.dll，并要求导出
#       crypto_sign_keypair / crypto_sign / crypto_sign_open
#   仓库里只有 C 源码，没有任何二进制，因此 CL-Falcon 生成会失败
#   （报「找不到可用的 falcon512.dll」）。
#
# 关于文件名：
#   代码里把路径硬编码为 `falcon512.dll`（源于原始 Windows 环境）。
#   ctypes.CDLL 不校验扩展名，只要内容是当前平台的共享库即可加载，
#   因此这里仍输出为 .dll 名称，同时另存一份 .so 便于人工识别。
#   放置位置取代码的查找顺序：
#       falcon/falcon512/falcon512int/falcon512.dll   ← 源码所在目录，优先
#       falcon/falcon512/falcon512.dll
#
# -DNDEBUG: 关闭断言，并让 FALCON_FPEMU 等实现选取走优化路径
# -fPIC   : 位置无关代码，共享库必需
#
# 必须额外编译 ../randombytes_openssl.c：
#   Falcon 的 nist.c 只声明 randombytes 而无定义（原由 NIST KAT 框架提供），
#   缺它会导致 `undefined symbol: randombytes`，ctypes.CDLL 直接失败。
# 需要链接 -lcrypto 提供 RAND_bytes。
# =============================================================================
set -euo pipefail

BACKEND_DIR="${1:-/backend}"
FALCON_DIR="$BACKEND_DIR/falcon"
SRC_DIR="$FALCON_DIR/falcon512/falcon512int"
RAND_SRC="$FALCON_DIR/randombytes_openssl.c"

cd "$SRC_DIR"

if [ ! -f "$RAND_SRC" ]; then
  echo "错误：缺少 $RAND_SRC（randombytes 实现）" >&2
  exit 1
fi

SRCS="codec.c common.c falcon.c fft.c fpr.c keygen.c nist.c rng.c shake.c sign.c vrfy.c $RAND_SRC"

OUT_A="$SRC_DIR/falcon512.dll"          # 代码查找顺序中的 ALT2
OUT_B="$FALCON_DIR/falcon512/falcon512.dll"  # ALT

echo "[1/2] 编译 Falcon-512 共享库"
gcc -shared -fPIC -O2 -DNDEBUG -I. -o "$OUT_A" $SRCS -lcrypto
echo "      -> $OUT_A"
cp "$OUT_A" "$OUT_B"
echo "      -> $OUT_B"

echo "[2/2] 校验导出符号"
for sym in crypto_sign_keypair crypto_sign crypto_sign_open; do
  if nm -D --defined-only "$OUT_A" 2>/dev/null | grep -q " $sym\$"; then
    echo "      OK   $sym"
  else
    echo "      MISS $sym   <-- 缺失会导致加载后 hasattr 校验失败"
  fi
done

echo
ls -la "$OUT_A" "$OUT_B"