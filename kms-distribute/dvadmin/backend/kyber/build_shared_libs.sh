#!/usr/bin/env bash
# =============================================================================
# 编译 PQClean Kyber 参考实现的共享库（.so）
# -----------------------------------------------------------------------------
# 为什么需要：
#   kms-distribute 的 PQKDS 后端（backend/pqkds/certificateless_kyber_dll_fusion.py）
#   通过 ctypes 加载 libpqcrystals_kyber{K}_ref.so 来生成 Kyber 密钥。
#   仓库里只有 PQClean 的 C 源码，没有任何 .so，因此 CL-Kyber / CL-Falcon
#   的密钥生成会失败（报「Kyber动态库未找到或不可加载」）。
#
# 关键点：
#   必须把 randombytes.c 一起编译 —— 否则产物会有
#   `undefined symbol: randombytes`，ctypes.CDLL 直接失败。
#   fips202 单独出库，供主库以 RTLD_GLOBAL 预加载。
#
# KYBER_K: 2=512, 3=768, 4=1024（对应安全级别）
# =============================================================================
set -euo pipefail

REF_DIR="${1:-/backend/kyber/ref}"
cd "$REF_DIR"
mkdir -p lib

SRCS="cbd.c fips202.c indcpa.c kem.c ntt.c poly.c polyvec.c randombytes.c reduce.c symmetric-shake.c verify.c"

echo "[1/2] 编译 fips202（共享库，供预加载）"
gcc -shared -fPIC -O2 -I. -o lib/libpqcrystals_fips202_ref.so fips202.c
echo "      -> lib/libpqcrystals_fips202_ref.so"

echo "[2/2] 编译 Kyber 三个变体"
for V in 512 768 1024; do
  case "$V" in
    512)  K=2 ;;
    768)  K=3 ;;
    1024) K=4 ;;
  esac
  gcc -shared -fPIC -O2 -DKYBER_K="$K" -I. \
      -o "lib/libpqcrystals_kyber${V}_ref.so" $SRCS
  echo "      -> lib/libpqcrystals_kyber${V}_ref.so (KYBER_K=$K)"
done

echo
echo "产物："
ls -la lib/*.so