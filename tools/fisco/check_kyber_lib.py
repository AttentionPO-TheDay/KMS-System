"""诊断 Kyber 共享库能否被 ctypes 加载。"""
import ctypes
import os

REF_LIB = "/backend/kyber/ref/lib"

libs = [
    "libpqcrystals_fips202_ref.so",
    "libpqcrystals_kyber512_ref.so",
    "libpqcrystals_kyber768_ref.so",
    "libpqcrystals_kyber1024_ref.so",
]

for name in libs:
    path = os.path.join(REF_LIB, name)
    if not os.path.exists(path):
        print(f"MISSING  {name}")
        continue
    try:
        ctypes.CDLL(path)
        print(f"OK       {name}")
    except OSError as exc:
        print(f"FAIL     {name}")
        print(f"         {exc}")

# 单独用 RTLD_GLOBAL 预加载 fips202 后再试 kyber
# （C 代码里 kyber 依赖 fips202 的符号）
print("\n--- 预加载 fips202 后再试 ---")
try:
    ctypes.CDLL(os.path.join(REF_LIB, "libpqcrystals_fips202_ref.so"),
                mode=getattr(ctypes, "RTLD_GLOBAL", 0))
    print("fips202 已全局预加载")
except OSError as exc:
    print(f"fips202 预加载失败: {exc}")

for name in libs[1:]:
    path = os.path.join(REF_LIB, name)
    try:
        ctypes.CDLL(path)
        print(f"OK       {name}")
    except OSError as exc:
        print(f"FAIL     {name}: {exc}")
