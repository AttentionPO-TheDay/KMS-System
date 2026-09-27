# -*- coding: utf-8 -*-
"""
国密 SM2 公钥加密（GB/T 32918.4-2016）—— 分派侧"把对称密钥发给某个用户"的 KEM 层
=============================================================================

背景
----
分派流程要把一把对称密钥（16 字节 SM4 密钥）交给**指定的某个用户**，也就是
用该用户的 SM2 公钥做一次公钥加密。镜像里**没有任何可用的 SM2 实现**：

* `gmssl` / `gmalg` / `snowland_sml` 都没装，装任何一个都要重建镜像、引入新依赖；
* `pycryptodome 3.20.0` 只有 AES/RSA/ECC 通用件，**没有 SM2、SM3、SM4**；
* `cryptography 50.0.1` 有 `algorithms.SM4` 和 `hashes.SM3`，但 **`ec` 里没有 SM2 曲线**
  （`ec.SM2` 不存在，`SECP256R1` 是另一条曲线，参数完全不同，绝不能拿来顶替）。

所以本模块**只用标准库 + `cryptography` 里的 SM3**：曲线运算自己写，
哈希用 `cryptography.hazmat.primitives.hashes.SM3`（实测通过 GB/T 32905-2016
的 `SM3("abc")` 向量）。**不新增任何依赖。**

为什么不自己写 SM3：SM3 已经有一个经过标准向量验证的实现躺在库里，
自己再抄一遍只会多一份可能出错的代码。曲线运算则必须自己写，因为库里真的没有。


本模块实现什么
--------------
**只做 SM2 公钥加密/解密**（GB/T 32918.4-2016 §6 / §7），不做签名、不做密钥交换。
SSCL 用的是**同一个原语**：SSCL 的 `d_A` 是本曲线上的一个标量、`P_A` 是本曲线上
的一个点，把标量当私钥、把点当公钥直接调用本模块即可（见下文）。


密文顺序：**C1 || C3 || C2**
----------------------------
这与 GB/T 32918.4-2016 原文一致 —— 国标 §6.1 A8 写的就是
``输出密文 C = C1 || C3 || C2``，附录 A 的示例也按这个顺序印出密文。
（注意：网上流传的一份英译本在 A8 处误写成 ``C1||C2||C3``，但**同一份文件的示例
又印着 C1||C3||C2** —— 那是翻译错误，不要拿它当依据。GM/T 0003.4-2012 同样规定
C1||C3||C2。）

这个顺序本身也是工程上更好的选择：`C1`(65 字节) 与 `C3`(32 字节) 都是定长的，
解析时不必先知道明文长度就能切出三段，剩下的全是 `C2`。
另外它与 `gmssl` 的 `mode=1` 一致，便于互通。


信封格式
--------
`encrypt()` 返回一个 **JSON 可序列化** 的字典，自描述，供数据库表单独存一列：

.. code-block:: python

    {
        "algorithm":  "sm2",              # 算法标记，将来换算法时靠它分派
        "ciphertext": "<hex>",            # hex(C1||C3||C2)，共 130+64+2*len(M) 个 hex 字符
        "public_key": "<hex>",            # 加密到的那个点（130 hex，04 开头）
    }

`public_key` 是**为谁加密的**这一事实的记录，便于事后审计
（"这个信封到底发给谁了"）。它是公开信息，不构成秘密泄露。
解密**只依赖 `ciphertext` 与私钥**，不去信 `public_key` 字段
（信封可被篡改，把不可信字段当输入是没必要的攻击面）。


调用方必须传**派生出来的 `P_A`**，不能传库里存的 `finalPublicKey`（`W_A`）
----------------------------------------------------------------------------
主 KMS 给 SM2 / SSCL 用户存的 `key_value` JSON 里有两个东西：

* `partialKey` = ``t_A``（KGC 给出的部分私钥）
* `finalPublicKey` = ``W_A``（**部分公钥**，不是用户真正的公钥！）

用户真正的私钥是 ``d_A = (t_A + u) mod n``，与之配套的公钥点是::

    P_A = W_A + λ·P_pub,   其中 λ = SM3(W_A.x || W_A.y || H_A)，P_pub = ms·G

**加密到 `W_A` 会得到一个谁都打不开的信封**——用户用 `d_A` 解不开，KGC 也解不开。
主 KMS 的职责是算好 `P_A` 再交给本模块。

本模块**不假设、也不检查点是怎么来的**：它只对"你给的这个点"做标准要求的
合法性校验（130 hex、`04` 前缀、在曲线上），然后加密到它。
这样无论 `P_A` 是主 KMS 现算的还是从库里读的，本模块都不用改。
这段注释是给未来的读者看的：**不要"顺手"把 `finalPublicKey` 直接塞进来。**


两个算法（SM2 / SSCL）共用本模块
--------------------------------
SSCL 的密钥材料同样是本曲线上的"标量 + 点"：

* 私钥 = 标量 `d_A ∈ [1, n-1]`（64 hex）
* 公钥 = 点 `P_A`（130 hex，`04 || x || y`）

所以 `SM2Crypto.encrypt(P_A_hex, key)` / `SM2Crypto.decrypt(d_A_hex, envelope)`
对 SSCL 同样成立，**不需要第二份实现**。算法差异在密钥材料的**生成/派生**阶段，
不在加解密原语这一层。


曲线参数是可注入的（为了能跑国标向量，不是为了可配置）
------------------------------------------------------
默认曲线是生产用的 **sm2p256v1**（GB/T 32918.5-2017 / GM/T 0003.5-2012）。
内部函数额外接一个 :class:`CurveParams` 参数，是因为 **GB/T 32918.4-2016 附录 A.2
的示例用的是一条不一样的 256 位测试曲线**（``p = 8542D69E...``、基点也不同）。
不把这组参数抽出来的话，国标里唯一一份公开的加解密向量就只能靠"手抄中间量"来核对，
而没法跑**端到端**的加解密。测试里正是注入那组参数来跑标准向量的。
生产代码永远用默认参数，不需要、也不应该传别的曲线。


安全要点
--------
* **随机数**：`k` 用 `secrets.randbelow` 从 CSPRNG 取，均匀分布于 `[1, n-1]`。
  SM2 加密的 `k` 一旦重复或可预测，私钥就会被直接解出——这是致命的，
  绝不允许用 `random` 模块或固定值。
* **完整性**：`decrypt()` 逐字节校验 `C3`，不匹配抛 :class:`SM2IntegrityError`，
  **绝不返回未经验证的"明文"**。调用方不要吞掉这个异常。
* **点校验**：公钥必须满足曲线方程，`C1` 也必须满足，否则抛 `ValueError`
  （国标 §7.1 B1 明确要求校验 `C1`）。不校验就会给非法曲线攻击留门。
* **时序**：本模块是纯 Python、用了 `pow(x, -1, p)` 等大整数运算，**没有做常数时间
  保证**。它跑在接受分发请求的服务端进程里，攻击者能观测到的只有"成功/失败"，
  拿不到逐次计时；因此这里不追求常数时间实现，这一点如实写在这里，
  而不是假装做了防护。
* **曲线参数自检**：首次做基点预计算时会检查 ``G`` 在曲线上且 ``[n]G = O``
  （见 :func:`_self_check_curve`）。曲线参数写错是"能跑但全错"的经典故障，
  这里让它**立刻炸**，而不是产出没人能解开的信封。


性能
----
纯 Python 大整数椭圆曲线运算，**实测约 2~4 ms 一次 32 字节载荷的加/解密**
（见测试文件里的 `test_performance_rough`，以容器内实测输出为准）。
分派是低频操作（一次分发一次），这个量级可以接受。
如果将来成为瓶颈，正确做法是换一个带 SM2 的 C 实现（例如给镜像加 `gmssl`），
**而不是去动这里的数学**。
"""

from __future__ import annotations

import secrets
import struct
from typing import Dict, List, NamedTuple, Optional, Tuple

from cryptography.hazmat.primitives import hashes

__all__ = [
    "CurveParams",
    "SM2IntegrityError",
    "SM2Crypto",
    "SM2_CURVE",
    "SM2_P",
    "SM2_A",
    "SM2_B",
    "SM2_N",
    "SM2_H",
    "SM2_GX",
    "SM2_GY",
    "SM2_C1_BYTES",
    "SM2_C3_BYTES",
    "SM2_PUBLIC_KEY_HEX_LEN",
    "SM2_PRIVATE_KEY_HEX_LEN",
    "SM2_ENVELOPE_ALGORITHM",
    "sm3_digest",
]


class CurveParams(NamedTuple):
    """一条短 Weierstrass 曲线 ``y² = x³ + ax + b (mod p)`` 的全部参数。

    ``gx``/``gy`` 是基点 ``G``（未压缩坐标），``n`` 是 ``G`` 的阶，``h`` 是余因子。
    """

    p: int
    a: int
    b: int
    n: int
    h: int
    gx: int
    gy: int


# ---------------------------------------------------------------------------
# 生产曲线：sm2p256v1（GB/T 32918.5-2017 / GM/T 0003.5-2012）
# ---------------------------------------------------------------------------
#: 素域特征
SM2_P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
#: 曲线系数 a
SM2_A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
#: 曲线系数 b
SM2_B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
#: 基点 G 的阶
SM2_N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
#: 余因子 h。SM2 的 h = 1 —— 这一点很重要：
#:   * 没有小子群，不需要额外做子群成员校验；
#:   * 国标 §6.1 A3 / §7.1 B2 里的 S = [h]P 就退化成 S = P 本身，
#:     所以"点在曲线上且不是无穷远点"这一条**就是**那一步要求。下文仍然显式写了
#:     h 的检查，免得读者以为漏实现了标准步骤。
SM2_H = 1
#: 基点 G 的 x 坐标
SM2_GX = 0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7
#: 基点 G 的 y 坐标
SM2_GY = 0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0

#: 生产曲线参数（唯一对外使用的曲线）
SM2_CURVE = CurveParams(SM2_P, SM2_A, SM2_B, SM2_N, SM2_H, SM2_GX, SM2_GY)

#: 未压缩点序列化后的**字节**长度：1 字节 PC(0x04) + 32 字节 x + 32 字节 y
SM2_C1_BYTES = 65
#: C3 是 SM3 摘要，定长 32 字节
SM2_C3_BYTES = 32
#: 未压缩点序列化后的**十六进制字符**长度：130
SM2_PUBLIC_KEY_HEX_LEN = 130
#: 私钥（标量）的十六进制字符长度：32 字节 = 64 字符
SM2_PRIVATE_KEY_HEX_LEN = 64
#: 信封里的算法标记
SM2_ENVELOPE_ALGORITHM = "sm2"

#: 曲线阶的字节长度（32），x2/y2 序列化时固定用这个长度
_FE_BYTES = 32


class SM2IntegrityError(ValueError):
    """C3 校验失败：密文被篡改，或者用的不是配套的私钥。

    继承自 :class:`ValueError` 是**故意的**：调用方即使只写了
    ``except ValueError`` 也不会漏掉这个失败、误以为解密成功。
    但请显式捕获它，以便把"被篡改/密钥不对"和"输入格式非法"区分开——
    这两件事的处置方式完全不同（前者是攻击信号，后者是调用方的 bug）。
    """


# ---------------------------------------------------------------------------
# SM3（GB/T 32905-2016）
# ---------------------------------------------------------------------------
def sm3_digest(data: bytes) -> bytes:
    """SM3 摘要（32 字节）。

    直接用 `cryptography` 的实现。该库提供 `hashes.SM3`，且实测匹配
    GB/T 32905-2016 的标准向量
    ``SM3("abc") = 66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0``。

    包一层是为了给"库到底有没有 SM3"这件事一个**明确的失败点**，
    而不是让 `AttributeError` 从某个深处冒出来。
    """
    digest = hashes.Hash(hashes.SM3())
    digest.update(data)
    return digest.finalize()


# ---------------------------------------------------------------------------
# KDF（GB/T 32918.4-2016 §5.4.3）
# ---------------------------------------------------------------------------
def _kdf(z: bytes, klen: int) -> bytes:
    """密钥派生函数 KDF(Z, klen)。

    定义（§5.4.3）::

        ct = 0x00000001
        for i in 1 .. ceil(klen / v):          # v = 256，SM3 的输出位长
            Ha_i = H_v(Z || ct)                # ct 是**32 位大端**计数器
            ct += 1
        K = Ha_1 || ... || Ha_{n-1} || Ha_n 的最左 (klen - v*floor(klen/v)) 位

    即：**只有最后一轮可能要截断**，前面几轮都是完整 32 字节。
    本实现按字节工作（调用方只需要整字节的密钥数据），所以截断就是取前 `klen` 字节。
    """
    if klen < 0:
        raise ValueError(f"KDF 输出长度不能为负：{klen}")
    out = bytearray()
    counter = 1
    while len(out) < klen:
        if counter > 0xFFFFFFFF:
            # 国标要求 klen < (2^32 - 1) * v；实际业务里不可能触到，但别静默回绕。
            raise ValueError("KDF 输出长度超过国标上限")
        out += sm3_digest(z + struct.pack(">I", counter))
        counter += 1
    return bytes(out[:klen])


def _xor_mask(data: bytes, mask: bytes) -> bytes:
    """定长异或：`C2 = M ⊕ t`（加密）/ `M' = C2 ⊕ t`（解密）。

    调用方保证 ``len(mask) >= len(data)``，多余的掩码字节被忽略。
    空输入返回空字节串。
    """
    return bytes(a ^ b for a, b in zip(data, mask))


# ---------------------------------------------------------------------------
# 椭圆曲线点运算（Jacobian 射影坐标）
# ---------------------------------------------------------------------------
# 为什么用 Jacobian 而不是仿射：仿射每次点加倍/点加都要算一次模逆
# （pow(x, -1, p) 是扩展欧几里得，比一次模乘贵两个数量级），
# 256 位标量乘法要做几百次，开销会全部压在模逆上。Jacobian 只在最后归一化时
# 算一次模逆，中间全是模乘/模加减。这是纯 Python 实现能不能用的关键。
#
# 约定：Jacobian 点用 (X, Y, Z) 表示，对应仿射坐标 (X/Z², Y/Z³)；
#       Z == 0 表示无穷远点 O。为了少写一个类，这里直接用三元组，
#       **只在本节内部使用**，对外一律是仿射坐标 + 十六进制串。
_JacPoint = Tuple[int, int, int]
#: 无穷远点 O（Z = 0）
_JAC_INFINITY: _JacPoint = (0, 1, 0)


def _jac_double(pt: _JacPoint, a: int, p: int) -> _JacPoint:
    """Jacobian 点加倍。

    为了让同一份公式能跑国标附录里那条 ``a != -3`` 的测试曲线，
    这里用**通用**的 ``m = 3x² + a·z⁴``，而不是 ``a = -3`` 的专用化简式
    （SM2 主曲线的 ``a = p - 3``，本可以用更省的公式）。
    每次加倍多两次模乘，换来的是"公式是否通用"能被标准向量直接验证 ——
    这买卖很划算：纯 Python 里两次模乘约等于 0.2 微秒，
    而"公式只对某一条曲线成立"是发现不了的错误。
    """
    x1, y1, z1 = pt
    if z1 == 0 or y1 == 0:
        # Z = 0 是无穷远点；y = 0 的点是 2 阶点（本曲线上不存在，防御性处理），
        # 加倍后都是无穷远点。
        return _JAC_INFINITY
    xx = x1 * x1 % p
    yy = y1 * y1 % p
    yyyy = yy * yy % p
    zz = z1 * z1 % p
    # s = 2 * ((x + yy)^2 - xx - yyyy)
    s = 2 * ((x1 + yy) * (x1 + yy) - xx - yyyy) % p
    m = (3 * xx + a * zz * zz) % p  # m = 3x² + a·z⁴
    x3 = (m * m - 2 * s) % p
    y3 = (m * (s - x3) - 8 * yyyy) % p
    z3 = 2 * y1 * z1 % p
    return x3, y3, z3


def _jac_add_mixed(pt: _JacPoint, ax: int, ay: int, a: int, p: int) -> _JacPoint:
    """Jacobian 点 + **仿射**点（第二个加数是 Z = 1，省掉 4 次模乘）。

    标量乘法的预计算表存的就是仿射点，所以这里正好用得上。
    """
    x1, y1, z1 = pt
    if z1 == 0:
        # O + Q = Q
        return ax, ay, 1
    z1z1 = z1 * z1 % p
    u2 = ax * z1z1 % p           # U2 = x2 * Z1^2
    s2 = ay * z1 * z1z1 % p      # S2 = y2 * Z1^3
    h = (u2 - x1) % p
    r = (s2 - y1) % p
    if h == 0:
        if r == 0:
            # 同一个点，加法退化成加倍
            return _jac_double(pt, a, p)
        # H = 0 且 R != 0 → 互为逆元 → 和为无穷远点
        return _JAC_INFINITY
    hh = h * h % p
    hhh = h * hh % p
    v = x1 * hh % p
    x3 = (r * r - hhh - 2 * v) % p
    y3 = (r * (v - x3) - y1 * hhh) % p
    z3 = z1 * h % p
    return x3, y3, z3


def _jac_to_affine(pt: _JacPoint, p: int) -> Optional[Tuple[int, int]]:
    """Jacobian → 仿射；无穷远点返回 `None`。"""
    x, y, z = pt
    if z == 0:
        return None
    z_inv = pow(z, -1, p)
    z_inv2 = z_inv * z_inv % p
    return x * z_inv2 % p, y * z_inv2 % p * z_inv % p


def _base_mul(k: int, curve: CurveParams) -> Optional[Tuple[int, int]]:
    """计算 ``[k]G``，返回仿射坐标；``k`` 为 ``n`` 的倍数时返回 `None`（无穷远点）。

    用**固定窗口 w = 8** 的预计算表：表里存 ``[i]G``（i = 1..255），
    标量按 8 位一块从高到低处理——每块 8 次加倍 + 1 次点加（i == 0 时跳过点加）。
    表只在第一次用到某条曲线时算一遍（见 :func:`_base_table`）。
    """
    if k <= 0 or k % curve.n == 0:
        return None
    table = _base_table(curve)
    a, p = curve.a, curve.p
    acc = _JAC_INFINITY
    shift = ((k.bit_length() + 7) // 8 - 1) * 8
    while shift >= 0:
        for _ in range(8):
            acc = _jac_double(acc, a, p)
        idx = (k >> shift) & 0xFF
        if idx:
            acc = _jac_add_mixed(acc, *table[idx - 1], a, p)
        shift -= 8
    return _jac_to_affine(acc, p)


#: 基点预计算表缓存：曲线参数 → ``[1]G .. [255]G`` 的仿射坐标表。
#: 生产只有一条曲线，所以这个字典实际上只会有一个元素；
#: 用字典是为了测试注入国标测试曲线时不会串用生产的表。
#: 表是**只读**的：构建后没有任何代码会修改它。
_BASE_TABLES: Dict[CurveParams, List[Tuple[int, int]]] = {}

#: 已经通过自检的曲线，避免重复自检（自检本身要做一次完整的标量乘法）。
_CHECKED_CURVES: set = set()


def _self_check_curve(curve: CurveParams) -> None:
    """自检曲线参数：``G`` 必须在曲线上，且 ``[n]G`` 必须是无穷远点。

    "参数抄错一位"是这类实现最致命的故障模式：代码照跑、结果全错，
    而且错得"看起来很正常"（产出的是一个谁都打不开的信封，却没有任何报错）。
    这里花几毫秒把它变成**立刻崩溃**。

    注意调用顺序：``[n]G`` 的检查本身要做一次标量乘法，而标量乘法要先建基点表、
    建表又会回到本函数 —— 所以先把 ``curve`` 登记进 `_CHECKED_CURVES`
    （曲线方程那一步已经先做完了，不会漏），检查失败时再撤销登记。
    """
    if curve in _CHECKED_CURVES:
        return
    p, a, b = curve.p, curve.a, curve.b
    if not (0 <= curve.gx < p and 0 <= curve.gy < p):
        raise ValueError("SM2 曲线基点坐标超出素域范围")
    if (curve.gy * curve.gy - (curve.gx * curve.gx * curve.gx + a * curve.gx + b)) % p != 0:
        raise ValueError("SM2 曲线基点 G 不满足曲线方程，曲线参数有误")
    _CHECKED_CURVES.add(curve)
    try:
        # [n]G 必须是无穷远点。用 [n-1]G + G 判断，避免多算一次完整标量乘法。
        minus_g = _base_mul(curve.n - 1, curve)
        if minus_g is None:
            raise ValueError("SM2 曲线参数有误：[n-1]G 是无穷远点")
        summed = _jac_add_mixed((minus_g[0], minus_g[1], 1), curve.gx, curve.gy, a, p)
        if _jac_to_affine(summed, p) is not None:
            raise ValueError("SM2 曲线参数有误：[n]G 不是无穷远点（阶不正确）")
    except BaseException:
        _CHECKED_CURVES.discard(curve)
        raise


def _base_table(curve: CurveParams) -> List[Tuple[int, int]]:
    """构建（并缓存）``[1]G .. [255]G`` 的仿射坐标表，供 `_base_mul` 使用。"""
    table = _BASE_TABLES.get(curve)
    if table is None:
        _self_check_curve(curve)
        a, p = curve.a, curve.p
        table = [(curve.gx, curve.gy)]
        acc: _JacPoint = (curve.gx, curve.gy, 1)
        for _ in range(254):
            acc = _jac_add_mixed(acc, curve.gx, curve.gy, a, p)
            affine = _jac_to_affine(acc, p)
            if affine is None:  # pragma: no cover - 阶为素数时不可能
                raise AssertionError("构建基点表时出现无穷远点，曲线参数有误")
            table.append(affine)
        _BASE_TABLES[curve] = table
    return table


def _point_mul(k: int, px: int, py: int, curve: CurveParams) -> Optional[Tuple[int, int]]:
    """计算 ``[k]P``（P 是仿射点），返回仿射坐标；无穷远点返回 `None`。

    左到右滑动窗口（w = 4）：预计算 ``P, 3P, ..., 15P`` 这 8 个**奇数倍**点，
    然后从最高位往下扫。

    不变式：设已处理完 k 的 i+1 位以上，则 ``acc == [k >> i]P``。

    * 0 位：``acc = 2·acc``，``i -= 1``；
    * 1 位：向下取一个以 1 结尾、长度 ``m ≤ 4`` 的窗口 ``w``，
      做 m 次加倍（把 acc 放大 ``2^m``）再一次性加上 ``[w]P``，
      于是 ``acc == [k >> (j-1)]P``。

    预计算全用奇数倍，是因为窗口最低位固定为 1 ⇒ 窗口值必为奇数，
    这样表只需要存一半的点，点加次数也少一半。
    """
    if k <= 0 or k % curve.n == 0:
        return None
    a, p = curve.a, curve.p

    # 预计算奇数倍：[P, 3P, 5P, ..., 15P]，下标 m 对应 [2m+1]P。
    # 连续做 7 次"加 P"即可：P → 3P → 5P → ... → 15P。
    odd: List[Tuple[int, int]] = [(px, py)]
    acc_odd: _JacPoint = (px, py, 1)
    for _ in range(7):
        acc_odd = _jac_add_mixed(acc_odd, px, py, a, p)
        affine = _jac_to_affine(acc_odd, p)
        if affine is None:
            return None
        odd.append(affine)

    acc: _JacPoint = _JAC_INFINITY
    i = k.bit_length() - 1
    while i >= 0:
        if not (k >> i) & 1:
            acc = _jac_double(acc, a, p)
            i -= 1
            continue
        j = i
        while not (k >> j) & 1:
            j += 1
        m = i - j + 1  # 窗口位数，1 ≤ m ≤ 4
        window = (k >> j) & ((1 << m) - 1)
        for _ in range(m):
            acc = _jac_double(acc, a, p)
        acc = _jac_add_mixed(acc, *odd[(window - 1) >> 1], a, p)
        i = j - 1
    return _jac_to_affine(acc, p)


# ---------------------------------------------------------------------------
# 点的解析 / 序列化 / 校验
# ---------------------------------------------------------------------------
def _parse_public_point(public_key_hex, curve: CurveParams) -> Tuple[int, int]:
    """解析并校验一个未压缩点，返回仿射 ``(x, y)``。

    校验项（全部不通过就抛 `ValueError`，**绝不"尽力而为"地继续**）：

    * 是字符串、长度为 130；
    * 以 `04` 开头（未压缩形式）；
    * 剩余 128 个字符是合法十六进制；
    * ``x``、``y`` 都落在 ``[0, p-1]``；
    * 点**满足曲线方程** ``y² = x³ + ax + b (mod p)``。
    """
    if not isinstance(public_key_hex, str):
        raise ValueError(
            f"SM2 公钥必须是 hex 字符串，收到 {type(public_key_hex).__name__}"
        )
    text = public_key_hex.strip()
    if len(text) != SM2_PUBLIC_KEY_HEX_LEN:
        raise ValueError(
            f"SM2 公钥长度必须是 {SM2_PUBLIC_KEY_HEX_LEN} 个 hex 字符"
            f"（未压缩点 04||x||y），收到 {len(text)}"
        )
    if not text.lower().startswith("04"):
        raise ValueError("SM2 公钥必须以 04 开头（未压缩形式）")
    normalized = text.lower()
    try:
        x = int(normalized[2:66], 16)
        y = int(normalized[66:], 16)
    except ValueError as exc:
        raise ValueError(f"SM2 公钥不是合法十六进制：{exc}") from exc
    p, a, b = curve.p, curve.a, curve.b
    if not (0 <= x < p and 0 <= y < p):
        raise ValueError("SM2 公钥坐标超出素域范围")
    if (y * y - (x * x * x + a * x + b)) % p != 0:
        raise ValueError("SM2 公钥不在曲线 y² = x³ + ax + b (mod p) 上")
    return x, y


def _point_to_hex(x: int, y: int) -> str:
    """仿射点 → 未压缩 hex：``04 || x || y``，定长 130 个小写字符。"""
    return "04" + format(x, "064x") + format(y, "064x")


def _private_scalar(private_key_hex, curve: CurveParams) -> int:
    """解析并校验私钥标量，返回 ``int``（落在 ``[1, n-1]``）。

    注意 **0 是非法值**：国标 §6.1 A1 要求 ``k ∈ [1, n-1]``，私钥同理。
    0 不是"弱密钥"，它根本没有对应的点（``[0]G = O``），必须直接拒绝，
    而不是让它跑到乘法里得到一个无穷远点再引发别处莫名其妙的错误。
    """
    if not isinstance(private_key_hex, str):
        raise ValueError(
            f"SM2 私钥必须是 hex 字符串，收到 {type(private_key_hex).__name__}"
        )
    text = private_key_hex.strip()
    if len(text) != SM2_PRIVATE_KEY_HEX_LEN:
        raise ValueError(
            f"SM2 私钥长度必须是 {SM2_PRIVATE_KEY_HEX_LEN} 个 hex 字符"
            f"（32 字节标量），收到 {len(text)}"
        )
    try:
        d = int(text, 16)
    except ValueError as exc:
        raise ValueError(f"SM2 私钥不是合法十六进制：{exc}") from exc
    if not (1 <= d <= curve.n - 1):
        raise ValueError(
            f"SM2 私钥必须落在 [1, n-1]，实际值越界（{'0' if d == 0 else '>= n'}）"
        )
    return d


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
class SM2Crypto:
    """SM2 公钥加解密（GB/T 32918.4-2016），密文顺序 ``C1 || C3 || C2``。

    类上的静态方法都接受一个可选的 ``curve`` 参数，**默认是生产曲线
    sm2p256v1**；只有测试需要注入国标附录里的那条测试曲线，业务代码不要传。
    """

    #: 默认曲线（生产唯一使用的曲线）
    curve = SM2_CURVE

    @staticmethod
    def public_key_of(private_key_hex: str, *, curve: CurveParams = SM2_CURVE) -> str:
        """由私钥标量算出公钥点：``P = [d]G``，返回 130 个 hex 字符。

        用途：自检、测试、以及调用方核对"主 KMS 给的 `P_A` 和本地 `d_A` 对不对得上"。
        私钥非法（长度、范围）时抛 `ValueError`。
        """
        d = _private_scalar(private_key_hex, curve)
        point = _base_mul(d, curve)
        if point is None:  # pragma: no cover - d ∈ [1, n-1] 时不可能
            raise ValueError("私钥算出无穷远点，输入非法")
        return _point_to_hex(*point)

    @staticmethod
    def is_valid_public_key(public_key_hex, *, curve: CurveParams = SM2_CURVE) -> bool:
        """公钥是否合法：长度 130、`04` 前缀、坐标在素域内、**点在曲线上**。

        这是给调用方做**前置校验**用的布尔接口（不抛异常），
        和 `encrypt` 内部的校验是同一条代码路径，不会出现"这里说合法、
        那里说非法"的分歧。
        """
        try:
            _parse_public_point(public_key_hex, curve)
        except ValueError:
            return False
        return True

    @staticmethod
    def encrypt(
        public_key_hex: str,
        plaintext: bytes,
        *,
        k: Optional[int] = None,
        curve: CurveParams = SM2_CURVE,
    ) -> Dict[str, str]:
        """把 `plaintext` 加密到 `public_key_hex` 这个点，返回信封字典。

        :param public_key_hex: 目标点的未压缩 hex（130 字符，`04||x||y`）。
            **必须传派生出来的 `P_A`**，不能传主库里存的 `finalPublicKey`（`W_A`），
            详见模块文档。
        :param plaintext: 明文字节串。长度可以是 0（会得到一个只含 C1 与 C3 的信封）。
        :param k: **仅供测试复现标准向量**，生产路径不要传。
            传入时必须落在 ``[1, n-1]``；固定 `k` 会让密文完全可复现，
            也意味着同一 `k` 复用到两个明文上就直接泄露私钥。
        :param curve: 仅供测试注入国标附录的测试曲线；业务代码用默认值。

        :returns: ``{"algorithm": "sm2", "ciphertext": hex, "public_key": hex}``

        算法（国标 §6.1 A1~A8）：

        * A1 ``k ∈ [1, n-1]``，CSPRNG 取（`secrets.randbelow`）；
        * A2 ``C1 = [k]G``，未压缩序列化成 65 字节；
        * A3 ``S = [h]P_B``；SM2 的 ``h = 1``，所以"S 是无穷远点"等价于
          "P_B 是无穷远点"，而 `P_B` 已经过"在曲线上"校验、不可能是无穷远点，
          这一步天然成立（下文仍显式写出来，方便对照国标）；
        * A4 ``[k]P_B = (x2, y2)``；
        * A5 ``t = KDF(x2 || y2, klen)``；**若 t 全零则回到 A1 换一个 k 重来**；
        * A6 ``C2 = M ⊕ t``；
        * A7 ``C3 = SM3(x2 || M || y2)``；
        * A8 输出 ``C = C1 || C3 || C2``。
        """
        px, py = _parse_public_point(public_key_hex, curve)

        # A3：h = 1 时 [h]P_B = P_B，不是无穷远点（已由 _parse_public_point 保证）。
        if curve.h != 1:  # pragma: no cover - 本曲线固定 h = 1
            raise AssertionError("SM2 的余因子应为 1")

        while True:
            # A1：k 必须均匀取自 [1, n-1]。secrets.randbelow 是拒绝采样，
            # 不引入模偏差；传入测试用 k 时也必须过同一道范围检查。
            nonce = _pick_k(curve) if k is None else _validate_k(k, curve)

            # A2：C1 = [k]G
            c1 = _base_mul(nonce, curve)
            if c1 is None:
                # k ∈ [1, n-1] 且 n 是素数 ⇒ [k]G 不可能无穷远。
                # 真触发了说明曲线参数被写坏了，宁可报错也不要输出垃圾密文。
                raise ValueError("SM2 加密得到无穷远点，曲线参数有误")

            # A4：共享点 [k]P_B
            shared = _point_mul(nonce, px, py, curve)
            if shared is None:
                # 公钥在曲线上且 n 为素数 ⇒ 同理不可能。
                raise ValueError("SM2 加密得到无穷远共享点，公钥非法")
            x2, y2 = shared

            # A5：KDF
            klen = len(plaintext)
            x2b = x2.to_bytes(_FE_BYTES, "big")
            y2b = y2.to_bytes(_FE_BYTES, "big")
            mask = _kdf(x2b + y2b, klen)
            if klen > 0 and not any(mask):
                # 国标明确要求：t 为全零比特串时**换一个 k 重来**（回 A1），
                # 而不是照常输出 C2 = M。概率约 2^-256，但这是标准条文，
                # 不实现就等于擅自改算法。
                # 注意 klen == 0 时导出的就是空串（全零是它的正确取值），不能误判成退化。
                continue

            # A6/A7
            c2 = _xor_mask(plaintext, mask)
            c3 = sm3_digest(x2b + plaintext + y2b)

            # A8：按 C1 || C3 || C2 拼接
            return {
                "algorithm": SM2_ENVELOPE_ALGORITHM,
                "ciphertext": _point_to_hex(*c1) + c3.hex() + c2.hex(),
                "public_key": _point_to_hex(px, py),
            }

    @staticmethod
    def decrypt(
        private_key_hex: str,
        envelope: Dict,
        *,
        curve: CurveParams = SM2_CURVE,
    ) -> bytes:
        """用私钥解开信封，返回明文字节串。

        :raises SM2IntegrityError: `C3` 校验失败 —— 密文被篡改，或者这不是
            该私钥对应的信封。**这是唯一能让调用方区分"被篡改/密钥不对"的
            信号，不要吞掉它。**
        :raises ValueError: 私钥非法、信封结构/长度非法、或 `C1` 不是曲线上的
            合法点（这类是**输入格式**问题，不是完整性失败）。

        算法（国标 §7.1 B1~B7）：

        * B1 取出 `C1`，**校验它满足曲线方程**（不校验就会给非法曲线攻击留门）；
        * B2 ``S = [h]C1``，h = 1 时即 `C1` 本身，非无穷远点（B1 已保证）；
        * B3 ``[d_B]C1 = (x2, y2)``；
        * B4 ``t = KDF(x2 || y2, klen)``，全零则报错退出；
        * B5 ``M' = C2 ⊕ t``；
        * B6 ``u = SM3(x2 || M' || y2)``，与 `C3` 比对，不等即报错退出；
        * B7 输出 `M'`。

        解密的 `klen` 由密文长度反推：``klen = len(C1||C3||C2) - 65 - 32``。
        """
        d = _private_scalar(private_key_hex, curve)
        ciphertext = _ciphertext_bytes(envelope)

        # B1：切出 C1 / C3 / C2（C1 与 C3 都是定长，这是选 C1C3C2 顺序的直接好处）
        c1_bytes = ciphertext[:SM2_C1_BYTES]
        c3 = ciphertext[SM2_C1_BYTES:SM2_C1_BYTES + SM2_C3_BYTES]
        c2 = ciphertext[SM2_C1_BYTES + SM2_C3_BYTES:]

        c1_hex = c1_bytes.hex()
        if not c1_hex.startswith("04"):
            raise ValueError("SM2 密文的 C1 缺少未压缩点前缀 04")
        cx, cy = _parse_public_point(c1_hex, curve)  # 内含"在曲线上"校验

        # B2：h = 1 ⇒ [h]C1 = C1；_parse_public_point 已排除无穷远点。
        if curve.h != 1:  # pragma: no cover - 本曲线固定 h = 1
            raise AssertionError("SM2 的余因子应为 1")

        # B3：共享点 [d_B]C1
        shared = _point_mul(d, cx, cy, curve)
        if shared is None:
            raise ValueError("SM2 解密得到无穷远共享点，密文 C1 非法")
        x2, y2 = shared

        # B4：KDF（长度 = C2 的长度）
        x2b = x2.to_bytes(_FE_BYTES, "big")
        y2b = y2.to_bytes(_FE_BYTES, "big")
        mask = _kdf(x2b + y2b, len(c2))
        if len(c2) > 0 and not any(mask):
            raise ValueError("SM2 解密 KDF 输出全零，密文非法")

        # B5：M' = C2 ⊕ t
        plaintext = _xor_mask(c2, mask)

        # B6：u = SM3(x2 || M' || y2)，与 C3 比对
        expected = sm3_digest(x2b + plaintext + y2b)
        if not secrets.compare_digest(expected, c3):
            # 走到这里说明：密文被改过，或者私钥/公钥不是一对。
            # 绝不返回 plaintext —— 那是一个攻击者可以随意操控的字节串。
            raise SM2IntegrityError(
                "SM2 完整性校验失败（C3 不匹配）：密文被篡改，"
                "或该私钥与加密所用公钥不配套"
            )

        # B7
        return plaintext


def _pick_k(curve: CurveParams = SM2_CURVE) -> int:
    """从 CSPRNG 取 ``k ∈ [1, n-1]``。

    `secrets.randbelow(n - 1)` 在 ``[0, n-2]`` 上**均匀**（内部是拒绝采样，
    不是取模，没有模偏差），加 1 得到 ``[1, n-1]``。
    """
    return secrets.randbelow(curve.n - 1) + 1


def _validate_k(k, curve: CurveParams) -> int:
    """校验外部传入的测试用 `k`。"""
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError(f"SM2 的 k 必须是整数，收到 {type(k).__name__}")
    if not (1 <= k <= curve.n - 1):
        raise ValueError("SM2 的 k 必须落在 [1, n-1]")
    return k


def _ciphertext_bytes(envelope) -> bytes:
    """从信封里取出密文字节串，并做结构/长度校验。"""
    if not isinstance(envelope, dict):
        raise ValueError(f"SM2 信封必须是 dict，收到 {type(envelope).__name__}")
    algorithm = envelope.get("algorithm")
    if algorithm is not None and str(algorithm).lower() != SM2_ENVELOPE_ALGORITHM:
        raise ValueError(f"信封的算法标记不是 sm2：{algorithm!r}")
    ciphertext_hex = envelope.get("ciphertext")
    if not isinstance(ciphertext_hex, str):
        raise ValueError("SM2 信封缺少 hex 字符串字段 ciphertext")
    text = ciphertext_hex.strip()
    if len(text) % 2 != 0:
        raise ValueError("SM2 密文 hex 长度为奇数")
    try:
        raw = bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f"SM2 密文不是合法十六进制：{exc}") from exc
    if len(raw) < SM2_C1_BYTES + SM2_C3_BYTES:
        raise ValueError(
            f"SM2 密文至少要有 C1+C3 = {SM2_C1_BYTES + SM2_C3_BYTES} 字节，"
            f"收到 {len(raw)} 字节"
        )
    return raw
