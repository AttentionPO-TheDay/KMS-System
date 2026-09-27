"""诊断 falcon512.dll 能否被 ctypes 加载，并检查所需符号。"""
import ctypes
import os

CANDIDATES = [
    "/backend/falcon/falcon512.dll",
    "/backend/falcon/falcon512/falcon512.dll",
    "/backend/falcon/falcon512/falcon512int/falcon512.dll",
]

NEEDED = ["crypto_sign_keypair", "crypto_sign", "crypto_sign_open"]

for path in CANDIDATES:
    print(f"--- {path}")
    if not os.path.exists(path):
        print("    不存在")
        continue
    try:
        dll = ctypes.CDLL(path)
        print("    CDLL 加载成功")
    except OSError as exc:
        print(f"    CDLL 失败: {exc}")
        continue
    missing = [s for s in NEEDED if not hasattr(dll, s)]
    if missing:
        print(f"    缺少符号: {missing}")
    else:
        print("    三个符号齐全 -> 可用")
