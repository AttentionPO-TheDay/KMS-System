# -*- coding: utf-8 -*-
"""
SM2 公钥加密的自测（分派侧"把对称密钥发给某个用户"的密码学底座）
=============================================================================

**为什么先写这个再让业务代码调用**：一次分发会不会变成"发出去但没人打得开"，
完全取决于这一个原语算得对不对。所以先用**国标原文附录里的标准向量**把它钉死，
再谈调用点。

覆盖：
  1. `public_key_of` 自检：已知标量、边界标量（d = 1 / n-1）、与国标给出的 d_B → P_B
  2. **GB/T 32918.4-2016 附录 A.2 示例2（F_p−256）标准向量**：
     SM3 预处理、KDF、C2、C3、C1 全部逐字节比对，并跑**端到端**加解密
     （这是**互通性证明**，不是自洽检查）
  3. 往返：随机密钥 + 明文长度 0 / 1 / 31 / 32 / 33 / 64 / 1000
  4. 失败路径必须失败**且失败得可区分**：
     篡改 C2 / C3 / C1、错误私钥 → `SM2IntegrityError`；
     非法公钥、非法私钥、非法信封 → `ValueError`（且绝不等于 integrity 错误）
  5. 独立性：用 `gmssl`（如果装了）双向互通；否则退化为"另一条代码路径复算"，
     并把用的是哪一种如实打印出来
  6. 每次加密的 C1 都不同（随机性）

关于国标向量的一个重要事实
--------------------------
**国标附录 A.2 示例2 用的是它自己的一条 256 位测试曲线，不是生产用的 sm2p256v1。**
（``p = 8542D69E...``、基点 ``G = 421DEBD6...`` —— 见下面的 `GB_CURVE`。）
一开始我拿示例里的 P_B / C1 去套 sm2p256v1 的曲线方程，全部不通过；
换成附录自己给的这组参数后，``[d_B]G == P_B``、``[k]G == C1``、
``[k]P_B == (x2,y2)``、``[n]G == O`` 全部成立。
所以本文件把这组参数作为 `CurveParams` 注入模块跑标准向量 ——
这也是模块的曲线运算必须写成通用公式（而不是 ``a = -3`` 专用化简）的原因。

运行方式（镜像里的代码是构建期烤进去的，所以用 docker cp 送进去跑）：

    docker cp "backend/pqkds/sm2_crypto.py"        dvadmin3-django:/backend/pqkds/
    docker cp "backend/tests/test_sm2_crypto.py"   dvadmin3-django:/backend/tests/
    docker exec -w /backend dvadmin3-django python tests/test_sm2_crypto.py

它同时兼容 pytest（函数名都是 test_*，断言都是裸 assert）。
"""

import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pqkds import sm2_crypto as sm2  # noqa: E402
from pqkds.sm2_crypto import (  # noqa: E402
    SM2_A,
    SM2_B,
    SM2_C1_BYTES,
    SM2_C3_BYTES,
    SM2_CURVE,
    SM2_GX,
    SM2_GY,
    SM2_N,
    SM2_P,
    SM2_PUBLIC_KEY_HEX_LEN,
    CurveParams,
    SM2Crypto,
    SM2IntegrityError,
    sm3_digest,
)


# ---------------------------------------------------------------------------
# 国标 GB/T 32918.4-2016 附录 A.2 示例2（F_p − 256）的原文取值
# ---------------------------------------------------------------------------
#: 附录给出的测试曲线参数（**注意：这不是 sm2p256v1**）
GB_CURVE = CurveParams(
    p=0x8542D69E4C044F18E8B92435BF6FF7DE457283915C45517D722EDB8B08F1DFC3,
    a=0x787968B4FA32C3FD2417842E73BBFEFF2F3C848B6831D7E0EC65228B3937E498,
    b=0x63E4C6D3B23B0C849CF84241484BFE48F61D59A5B16BA06E6E12D1DA27C5249A,
    n=0x8542D69E4C044F18E8B92435BF6FF7DD297720630485628D5AE74EE7C32E79B7,
    h=1,
    gx=0x421DEBD61B62EAB6746434EBC3CC315E32220B3BADD50BDC4C4E6C147FEDD43D,
    gy=0x0680512BCBB42C07D47349D2153B70C4E5D7FDFCBFA36EA1A85841B9E46E09A2,
)
#: 私钥 d_B
GB_DB = "1649AB77A00637BD5E2EFE283FBF353534AA7F7CB89463F208DDBC2920BB0DA0"
#: 公钥 P_B = (x_B, y_B)，未压缩形式 04||x_B||y_B
GB_PB = (
    "04435B39CCA8F3B508C1488AFC67BE491A0F7BA07E581A0E4849A5CF70628A7E0A"
    "75DDBA78F15FEECB4C7895E2C1CDF5FE01DEBB2CDBADF45399CCF77BBA076A42"
)
#: 附录给出的随机数 k
GB_K = int("4C62EEFD6ECFC2B95B92FD6C3D9575148AFA17425546D49018E5388D49DD7B4F", 16)
#: 待加密消息 M："encryption standard"
GB_M = b"encryption standard"
#: 附录给出的 [k]G = C1（未压缩，130 hex）
GB_C1 = (
    "04245C26FB68B1DDDDB12C4B6BF9F2B6D5FE60A383B0D18D1C4144ABF17F6252E7"
    "76CB9264C2A7E88E52B19903FDC47378F605E36811F5C07423A24B84400F01B8"
)
#: 附录给出的 [k]P_B = (x2, y2)
GB_X2 = "64D20D27D0632957F8028C1E024F6B02EDF23102A566C932AE8BD613A8E865FE"
GB_Y2 = "58D225ECA784AE300A81A2D48281A828E1CEDF11C4219099840265375077BF78"
#: 附录给出的 t = KDF(x2 || y2, 152)
GB_T = "006E30DAE231B071DFAD8AA379E90264491603"
#: 附录给出的 C2 = M ⊕ t
GB_C2 = "650053A89B41C418B0C3AAD00D886C00286467"
#: 附录给出的 C3 = Hash(x2 || M || y2)
GB_C3 = "9C3D7360C30156FAB7C80A0276712DA9D8094A634B766D3A285E07480653426D"

#: 往返要跑标量乘法，给个宽松但真实的单次耗时上限（毫秒）
_SLOW_OP_MS = 3000.0


def _hex_field(value: str) -> int:
    """把国标原文那种"每 4 字节一组、带空格"的十六进制读成整数。"""
    return int(value.replace(" ", ""), 16)


def _fresh_scalar(curve: CurveParams = SM2_CURVE) -> str:
    """随机取一个合法私钥标量（64 hex，落在 [1, n-1]）。"""
    while True:
        candidate = os.urandom(32)
        value = int.from_bytes(candidate, "big")
        if 1 <= value <= curve.n - 1:
            return candidate.hex()


# ---------------------------------------------------------------------------
# 1. public_key_of 自检
# ---------------------------------------------------------------------------
def test_public_key_of_generator():
    """d = 1 时 P = G —— 这是曲线参数本身的自检（G 必须在曲线上、必须是这个 G）。"""
    assert SM2Crypto.public_key_of("00" * 31 + "01") == (
        "04" + format(SM2_GX, "064x") + format(SM2_GY, "064x")
    )


def test_public_key_of_gb_vector():
    """d = d_B 必须算出国标附录里给出的那个 P_B（**用附录自己的测试曲线**）。

    这一条同时钉死四件事：曲线参数、标量乘法、未压缩点序列化格式、
    以及"换一组参数也能算对"（说明公式是通用的，不是碰巧对 sm2p256v1 成立）。
    """
    got = SM2Crypto.public_key_of(GB_DB, curve=GB_CURVE)
    assert got == GB_PB.lower(), f"P_B 不匹配\n  期望 {GB_PB.lower()}\n  实际 {got}"


def test_gb_curve_params_are_consistent():
    """先把注入的测试曲线本身验一遍，免得后面用一条错曲线"验"出错误结论。"""
    p, a, b = GB_CURVE.p, GB_CURVE.a, GB_CURVE.b
    for name, (x, y) in {
        "G": (GB_CURVE.gx, GB_CURVE.gy),
        "P_B": (int(GB_PB[2:66], 16), int(GB_PB[66:], 16)),
        "C1": (int(GB_C1[2:66], 16), int(GB_C1[66:], 16)),
        "(x2,y2)": (int(GB_X2, 16), int(GB_Y2, 16)),
    }.items():
        assert (y * y - (x * x * x + a * x + b)) % p == 0, f"{name} 不在国标测试曲线上"
    # 附录的测试曲线同样不是 sm2p256v1，否则"注入曲线"这件事就没意义了
    assert GB_CURVE.p != SM2_P and GB_CURVE.gx != SM2_GX


def test_public_key_of_is_on_curve_and_well_formed():
    """若干随机标量算出的点都必须是"长度 130 / 04 开头 / 在曲线上"的合法公钥。"""
    for _ in range(6):
        point = SM2Crypto.public_key_of(_fresh_scalar())
        assert len(point) == SM2_PUBLIC_KEY_HEX_LEN, f"长度不对：{len(point)}"
        assert point.startswith("04"), "缺少未压缩前缀 04"
        assert SM2Crypto.is_valid_public_key(point), f"算出来的点不在曲线上：{point}"


def test_public_key_of_boundary_scalars():
    """边界标量：d = n-1 得到 -G；d = n / 2n / n+1 都必须被拒。"""
    # d = n - 1 ⇒ P = [n-1]G = -G = (x_G, p - y_G)
    minus_g = "04" + format(SM2_GX, "064x") + format(SM2_P - SM2_GY, "064x")
    assert SM2Crypto.public_key_of((SM2_N - 1).to_bytes(32, "big").hex()) == minus_g

    # d = n 会算出无穷远点（[n]G = O），没有合法公钥可言；
    # 2n / n+1 越界，同样必须拒绝 —— 而不是返回 None 或抛别的错。
    for bad in (SM2_N, 2 * SM2_N, SM2_N + 1):
        bad_hex = format(bad, "064x")  # 2n 是 65 位 hex，长度检查会先拒
        try:
            SM2Crypto.public_key_of(bad_hex)
        except ValueError:
            continue
        raise AssertionError(f"d = {bad:#x} 竟然算出了公钥")

    # 反过来也要验一遍：n-1 是**合法**私钥，必须能用（否则上面的断言可能是"全拒"通过）
    assert SM2Crypto.public_key_of(format(SM2_N - 1, "064x")) == minus_g


def test_public_key_of_rejects_non_scalars():
    """d = 0 不是"弱密钥"而是非法值（[0]G = O），必须 ValueError。"""
    for bad in ("00" * 32, "0" * 64, "zz" * 32, "01" * 31, "01" * 33, "", None, 123):
        try:
            SM2Crypto.public_key_of(bad)
        except ValueError:
            continue
        raise AssertionError(f"非法私钥 {bad!r} 竟然被接受了")


# ---------------------------------------------------------------------------
# 2. GB/T 32918.4-2016 附录 A.2 示例2 标准向量
# ---------------------------------------------------------------------------
def test_gb_vector_sm3_abc():
    """先钉 SM3 本身：GB/T 32905-2016 的 SM3("abc") 向量。

    后面的 C3 / KDF 全部建立在 SM3 正确之上，这一条是它们的地基。
    """
    got = sm3_digest(b"abc").hex()
    assert got == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0", got


def test_gb_vector_preprocessing():
    """附录逐步给出的中间量：P_B = [d_B]G、[k]G = C1、[k]P_B = (x2, y2)。

    这三步覆盖了本模块**全部**的曲线运算路径（基点乘 + 一般点乘），
    任何一处算法写错都会在这里露出来。
    """
    assert SM2Crypto.public_key_of(GB_DB, curve=GB_CURVE) == GB_PB.lower()

    c1 = sm2._base_mul(GB_K, GB_CURVE)
    assert c1 is not None
    assert sm2._point_to_hex(*c1) == GB_C1.lower(), "C1 = [k]G 不匹配"

    shared = sm2._point_mul(GB_K, int(GB_PB[2:66], 16), int(GB_PB[66:], 16), GB_CURVE)
    assert shared is not None
    x2, y2 = shared
    assert f"{x2:064x}" == GB_X2.lower(), "x2 不匹配"
    assert f"{y2:064x}" == GB_Y2.lower(), "y2 不匹配"


def test_gb_vector_kdf_and_c2():
    """KDF(x2||y2, 152) 与 C2 = M ⊕ t 必须逐字节等于附录给出的值。"""
    t = sm2._kdf(bytes.fromhex(GB_X2) + bytes.fromhex(GB_Y2), len(GB_M))
    assert t.hex() == GB_T.lower(), f"KDF 不匹配：附录 {GB_T}，实际 {t.hex()}"

    c2 = sm2._xor_mask(GB_M, t)
    assert c2.hex() == GB_C2.lower(), f"C2 不匹配：附录 {GB_C2}，实际 {c2.hex()}"
    # 顺带确认 M ⊕ t ⊕ t = M（异或掩码的自反性，解密路径就靠它）
    assert sm2._xor_mask(c2, t) == GB_M

    # 反向验证 KDF 的边界：空输入导出空串；导出长度按字节严格对齐
    assert sm2._kdf(b"x", 0) == b""
    for n in (1, 31, 32, 33, 64, 100):
        assert len(sm2._kdf(b"probe", n)) == n


def test_gb_vector_c3():
    """C3 = SM3(x2 || M || y2) 必须等于附录给出的值。"""
    got = sm3_digest(bytes.fromhex(GB_X2) + GB_M + bytes.fromhex(GB_Y2)).hex()
    assert got == GB_C3.lower(), f"C3 不匹配：附录 {GB_C3}，实际 {got}"


def test_gb_vector_full_encrypt_and_decrypt():
    """整体对齐：用附录的 k 和公钥加密，密文必须与附录逐字节一致，且能解回原文。

    这是本文件**最强**的一条：它不是"我们自己能解开自己"，
    而是与国标原文给出的字节串完全相同 —— 任何自洽但错误的实现都过不了。
    """
    envelope = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)
    expected = (GB_C1 + GB_C3 + GB_C2).lower()  # 国标 A8：C = C1 || C3 || C2
    assert envelope["ciphertext"] == expected, (
        "与国标附录密文不一致\n  期望 " + expected + "\n  实际 " + envelope["ciphertext"]
    )
    assert envelope["algorithm"] == "sm2"
    assert envelope["public_key"] == GB_PB.lower()
    assert SM2Crypto.decrypt(GB_DB, envelope, curve=GB_CURVE) == GB_M


def test_gb_vector_ciphertext_ordering_is_c1c3c2():
    """把顺序钉死：前 65 字节是 C1、接着 32 字节是 C3、剩下的是 C2。

    国标 §6.1 A8 写的就是 ``C = C1 || C3 || C2``（附录示例也按此印出密文），
    这里再显式断言一次，免得将来有人改成别的顺序而没人发现。
    """
    envelope = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)
    ct = envelope["ciphertext"]
    assert ct[:130] == GB_C1.lower()
    assert ct[130:194] == GB_C3.lower()
    assert ct[194:] == GB_C2.lower()
    # 若误用 C1||C2||C3，切出来的三段长度虽然一样，内容必然不同
    assert ct != (GB_C1 + GB_C2 + GB_C3).lower()
    assert len(ct) == 2 * (SM2_C1_BYTES + SM2_C3_BYTES + len(GB_M))


def test_gb_vector_rejects_wrong_curve():
    """反向对照：**同一条密文拿到生产曲线 sm2p256v1 上必须解不开**。

    这一条防的是"曲线参数其实没生效、一直在用默认曲线"这种假通过 ——
    如果注入参数被忽略，上面那些向量测试反而会以另一种方式失败；
    这里再明确一次两条曲线确实不同。
    """
    envelope = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)
    # 国标附录的公钥在 sm2p256v1 上根本不是合法点
    assert not SM2Crypto.is_valid_public_key(GB_PB)
    assert SM2Crypto.is_valid_public_key(GB_PB, curve=GB_CURVE)
    try:
        SM2Crypto.decrypt(GB_DB, envelope)
    except ValueError:
        pass
    else:
        raise AssertionError("国标测试曲线的密文竟然在 sm2p256v1 上解开了")


def test_gb_vector_192_bit_example1():
    """附录 A.2 示例1（F_p−192）—— 再换一条**参数不同**的曲线，验证公式通用性。

    本模块只服务 sm2p256v1，所以这里不跑模块，而是把模块使用的
    Jacobian 公式（通用加倍 + 混合加法）原样搬到 192 位参数下，
    看 ``[d_B]G`` 是否落回附录给出的 ``(x_B, y_B)``。

    * 证明：公式对第三组曲线参数同样成立 ⇒ 曲线运算不是"恰好对某一条蒙对"；
    * 不证明：互操作性（那由示例2 的逐字节向量负责）。
    """
    p192 = _hex_field("BDB6F4FE 3E8B1D9E 0DA8C0D4 6F4C318C EFE4AFE3 B6B8551F")
    a192 = _hex_field("BB8E5E8F BC115E13 9FE6A814 FE48AAA6 F0ADA1AA 5DF91985")
    gx = _hex_field("4AD5F704 8DE709AD 51236DE6 5E4D4B48 2C836DC6 E4106640")
    gy = _hex_field("02BB3A02 D4AAADAC AE24817A 4CA3A1B0 14B52704 32DB27D2")
    db = _hex_field("58892B80 7074F53F BF67288A 1DFAA1AC 313455FE 60355AFD")
    xb = _hex_field("79F0A954 7AC6D100 531508B3 0D30A565 36BCFC81 49F4AF4A")
    yb = _hex_field("AE38F2D8 890838DF 9C19935A 65A8BCC8 994BC792 4672F912")

    # 与本模块 _jac_double / _jac_add_mixed 同构，只把 (p, a) 变成参数
    def double(pt):
        x1, y1, z1 = pt
        if z1 == 0 or y1 == 0:
            return (0, 1, 0)
        xx = x1 * x1 % p192
        yy = y1 * y1 % p192
        yyyy = yy * yy % p192
        zz = z1 * z1 % p192
        s = 2 * ((x1 + yy) * (x1 + yy) - xx - yyyy) % p192
        m = (3 * xx + a192 * zz * zz) % p192
        x3 = (m * m - 2 * s) % p192
        return x3, (m * (s - x3) - 8 * yyyy) % p192, 2 * y1 * z1 % p192

    def add_mixed(pt, ax, ay):
        x1, y1, z1 = pt
        if z1 == 0:
            return ax, ay, 1
        z1z1 = z1 * z1 % p192
        u2 = ax * z1z1 % p192
        s2 = ay * z1 * z1z1 % p192
        h = (u2 - x1) % p192
        r = (s2 - y1) % p192
        if h == 0:
            return double(pt) if r == 0 else (0, 1, 0)
        hh = h * h % p192
        hhh = h * hh % p192
        v = x1 * hh % p192
        x3 = (r * r - hhh - 2 * v) % p192
        return x3, (r * (v - x3) - y1 * hhh) % p192, z1 * h % p192

    # 逐比特 double-and-add（不引入本模块的滑动窗口）
    acc = (0, 1, 0)
    for bit in bin(db)[2:]:
        acc = double(acc)
        if bit == "1":
            acc = add_mixed(acc, gx, gy)
    x, y, z = acc
    assert z != 0, "192 位域下算出了无穷远点"
    z_inv = pow(z, -1, p192)
    assert x * z_inv * z_inv % p192 == xb, "192 位域下 x 坐标不匹配"
    assert y * z_inv ** 3 % p192 == yb, "192 位域下 y 坐标不匹配"


# ---------------------------------------------------------------------------
# 3. 往返（随机密钥、各种长度）
# ---------------------------------------------------------------------------
def test_roundtrip_various_plaintext_sizes():
    """随机密钥 × 长度 0/1/31/32/33/64/1000 的往返，并顺带校验信封形状。"""
    for size in (0, 1, 31, 32, 33, 64, 1000):
        private_key = _fresh_scalar()
        public_key = SM2Crypto.public_key_of(private_key)
        plaintext = os.urandom(size)

        envelope = SM2Crypto.encrypt(public_key, plaintext)
        assert envelope["algorithm"] == "sm2"
        assert envelope["public_key"] == public_key
        assert set(envelope) == {"algorithm", "ciphertext", "public_key"}
        # 长度关系：65 + 32 + len(M) 字节 ⇒ 2 倍个 hex 字符
        assert len(envelope["ciphertext"]) == 2 * (SM2_C1_BYTES + SM2_C3_BYTES + size), (
            f"size={size} 密文长度不对：{len(envelope['ciphertext'])}"
        )
        assert SM2Crypto.decrypt(private_key, envelope) == plaintext, f"size={size} 往返失败"


def test_roundtrip_many_random_pairs():
    """多组随机密钥/明文，确认没有"偶尔才对"的路径。"""
    for _ in range(12):
        private_key = _fresh_scalar()
        public_key = SM2Crypto.public_key_of(private_key)
        plaintext = os.urandom(1 + (int.from_bytes(os.urandom(2), "big") % 200))
        envelope = SM2Crypto.encrypt(public_key, plaintext)
        assert SM2Crypto.decrypt(private_key, envelope) == plaintext


def test_roundtrip_high_bit_plaintext():
    """全 0xFF / 全 0x00 明文，避免"恰好异或成自己"之类的伪通过。"""
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    for plaintext in (b"\x00" * 32, b"\xff" * 32, bytes(range(256))):
        envelope = SM2Crypto.encrypt(public_key, plaintext)
        assert SM2Crypto.decrypt(private_key, envelope) == plaintext


def test_envelope_is_json_serializable():
    """信封要能直接塞进 JSON 列（数据库单独一列存它）。"""
    private_key = _fresh_scalar()
    envelope = SM2Crypto.encrypt(SM2Crypto.public_key_of(private_key), b"session-key")
    roundtripped = json.loads(json.dumps(envelope))
    assert roundtripped == envelope
    assert SM2Crypto.decrypt(private_key, roundtripped) == b"session-key"


# ---------------------------------------------------------------------------
# 4. 失败路径：必须失败，而且失败得**可区分**
# ---------------------------------------------------------------------------
def _expect_integrity_error(fn, what):
    """要求抛 `SM2IntegrityError`（而不是别的异常、更不是静默返回明文）。"""
    try:
        result = fn()
    except SM2IntegrityError:
        return
    except Exception as exc:
        raise AssertionError(
            f"{what} 抛了 {type(exc).__name__}: {exc}，期望 SM2IntegrityError"
        ) from exc
    raise AssertionError(f"{what} 竟然没有报错，还返回了 {result!r}")


def _expect_value_error(fn, what):
    """要求抛 `ValueError`；**若抛的是 `SM2IntegrityError` 则算不合格**。

    因为这两件事的处置完全不同：格式错误是调用方的 bug（可重试/该修代码），
    完整性失败是攻击或密钥不匹配的信号（该告警）。混在一起就无法分派。
    """
    try:
        fn()
    except SM2IntegrityError as exc:
        raise AssertionError(
            f"{what} 抛了 SM2IntegrityError（应为 ValueError）：{exc}"
        ) from exc
    except ValueError:
        return
    raise AssertionError(f"{what} 没有抛 ValueError")


def _sample_envelope(size=32):
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = os.urandom(size)
    return private_key, public_key, plaintext, SM2Crypto.encrypt(public_key, plaintext)


def test_tampered_c2_raises_integrity_error():
    """改 C2 的任意一位：C3 必然对不上 —— 必须 SM2IntegrityError，绝不返回明文。"""
    private_key, _, plaintext, envelope = _sample_envelope()
    # 先确认样本本身能解开，否则后面的"失败"可能只是样本坏了
    assert SM2Crypto.decrypt(private_key, envelope) == plaintext

    ct = bytearray.fromhex(envelope["ciphertext"])
    c2_start = SM2_C1_BYTES + SM2_C3_BYTES
    for index in (c2_start, c2_start + 7, len(ct) - 1):  # C2 的首字节 / 中间 / 末字节
        tampered = bytearray(ct)
        tampered[index] ^= 0x01
        bad = dict(envelope, ciphertext=bytes(tampered).hex())
        _expect_integrity_error(
            lambda bad=bad: SM2Crypto.decrypt(private_key, bad), f"篡改 C2[byte {index}]"
        )


def test_tampered_c3_raises_integrity_error():
    """改 C3 的任意一位：必须 SM2IntegrityError。"""
    private_key, _, _, envelope = _sample_envelope()
    ct = bytearray.fromhex(envelope["ciphertext"])
    for index in (SM2_C1_BYTES, SM2_C1_BYTES + SM2_C3_BYTES - 1):
        tampered = bytearray(ct)
        tampered[index] ^= 0x80
        bad = dict(envelope, ciphertext=bytes(tampered).hex())
        _expect_integrity_error(
            lambda bad=bad: SM2Crypto.decrypt(private_key, bad), f"篡改 C3[byte {index}]"
        )


def test_tampered_c1_never_returns_plaintext():
    """改 C1：要么点不合法（ValueError），要么算出的共享点不对（SM2IntegrityError）。

    **唯一不可接受的结果是返回明文。** 这条比"必须抛某个特定异常"更本质：
    C1 被改之后，我们只要求"绝不静默成功"。
    """
    private_key, _, _, envelope = _sample_envelope()
    ct = bytearray.fromhex(envelope["ciphertext"])
    checked = 0
    for index in (1, 32, 33, 64):  # C1 里的 x / y 各取几位
        tampered = bytearray(ct)
        tampered[index] ^= 0x01
        bad = dict(envelope, ciphertext=bytes(tampered).hex())
        try:
            result = SM2Crypto.decrypt(private_key, bad)
        except (ValueError, SM2IntegrityError):
            checked += 1
            continue
        raise AssertionError(f"篡改 C1[byte {index}] 之后竟然解出了 {result!r}")
    assert checked == 4

    # 另一类：把 C1 整体换成另一个**合法**点（在曲线上，但不是 [k]G）。
    # 这种是最危险的"看起来很干净"的篡改 —— 必须被 C3 挡住。
    other_c1 = bytes.fromhex(SM2Crypto.public_key_of(_fresh_scalar()))
    bad = dict(envelope, ciphertext=(other_c1 + ct[SM2_C1_BYTES:]).hex())
    _expect_integrity_error(
        lambda: SM2Crypto.decrypt(private_key, bad), "替换成合法的别的 C1"
    )


def test_wrong_private_key_raises_integrity_error():
    """用不配套的私钥解密：SM2IntegrityError（不是 ValueError —— 信封本身没坏）。"""
    _, _, _, envelope = _sample_envelope()
    wrong = _fresh_scalar()
    assert SM2Crypto.public_key_of(wrong) != envelope["public_key"]
    _expect_integrity_error(lambda: SM2Crypto.decrypt(wrong, envelope), "错误私钥")


def test_malformed_public_key_rejected_by_encrypt():
    """公钥格式非法：长度错、前缀错、坐标越界、**不在曲线上** —— 一律 ValueError。"""
    valid = SM2Crypto.public_key_of(_fresh_scalar())
    on_curve_bad_prefix = "05" + valid[2:]

    # 构造一个长度对、前缀对、但不在曲线上的点：把 y 改掉。
    x = int(valid[2:66], 16)
    y = int(valid[66:], 16)
    off_curve = "04" + format(x, "064x") + format((y + 1) % SM2_P, "064x")
    if SM2Crypto.is_valid_public_key(off_curve):  # pragma: no cover - 实际不会进
        off_curve = "04" + format(x, "064x") + format((y + 2) % SM2_P, "064x")

    candidates = [
        ("长度少 2 个字符", valid[:-2]),
        ("长度多 2 个字符", valid + "00"),
        ("没有 04 前缀", valid[2:] + "00"),
        ("前缀是 05", on_curve_bad_prefix),
        ("不是十六进制", "04" + "zz" * 64),
        ("坐标越界", "04" + format(SM2_P, "064x") + format(y, "064x")),
        ("点不在曲线上", off_curve),
        ("无穷远点编码", "04" + "00" * 64),
        ("空串", ""),
        ("bytes 而不是 str", bytes.fromhex(valid)),
        ("None", None),
    ]
    for what, bad_key in candidates:
        _expect_value_error(
            lambda bad_key=bad_key: SM2Crypto.encrypt(bad_key, b"x"), f"公钥{what}"
        )
        assert not SM2Crypto.is_valid_public_key(bad_key), f"is_valid_public_key 放过了：{what}"

    # 正样本：合法公钥必须被接受（免得上面的断言其实是因为全都失败而通过）
    assert SM2Crypto.is_valid_public_key(valid)
    assert SM2Crypto.is_valid_public_key(valid.upper())
    assert SM2Crypto.is_valid_public_key("  " + valid + "  ")


def test_malformed_private_key_rejected():
    """私钥非法：0 / >= n / 长度错 / 非十六进制 —— 一律 ValueError。"""
    candidates = [
        ("0", "00" * 32),
        ("n", format(SM2_N, "064x")),
        ("n+1", format(SM2_N + 1, "064x")),
        ("全 f", "ff" * 32),
        ("少 2 个字符", "01" * 31),
        ("多 2 个字符", "01" * 33),
        ("非十六进制", "zz" * 32),
        ("空串", ""),
        ("None", None),
    ]
    _, _, _, envelope = _sample_envelope()
    for what, bad_key in candidates:
        _expect_value_error(
            lambda bad_key=bad_key: SM2Crypto.decrypt(bad_key, envelope), f"私钥{what}"
        )
        _expect_value_error(
            lambda bad_key=bad_key: SM2Crypto.public_key_of(bad_key),
            f"public_key_of 私钥{what}",
        )


def test_malformed_envelope_rejected():
    """信封结构非法：不是 dict、缺字段、hex 非法、长度不足、算法标记不对。"""
    private_key, _, _, envelope = _sample_envelope()
    ct = envelope["ciphertext"]

    _expect_value_error(lambda: SM2Crypto.decrypt(private_key, None), "信封是 None")
    _expect_value_error(lambda: SM2Crypto.decrypt(private_key, ct), "信封是字符串")
    _expect_value_error(lambda: SM2Crypto.decrypt(private_key, {}), "信封缺 ciphertext")
    _expect_value_error(
        lambda: SM2Crypto.decrypt(private_key, {"ciphertext": 123}), "ciphertext 不是字符串"
    )
    _expect_value_error(
        lambda: SM2Crypto.decrypt(private_key, {"ciphertext": "zz"}), "ciphertext 非十六进制"
    )
    _expect_value_error(
        lambda: SM2Crypto.decrypt(private_key, {"ciphertext": ct[:96]}), "密文短于 C1+C3"
    )
    _expect_value_error(
        lambda: SM2Crypto.decrypt(private_key, {"algorithm": "rsa", "ciphertext": ct}),
        "算法标记不是 sm2",
    )
    _expect_value_error(
        lambda: SM2Crypto.decrypt(
            private_key,
            {"ciphertext": ct[: 2 * (SM2_C1_BYTES + SM2_C3_BYTES) - 1]},
        ),
        "密文 hex 长度为奇数",
    )
    # 明文恰好为空时，密文长度正好是 C1+C3（边界，必须能正常解开）
    empty_envelope = SM2Crypto.encrypt(envelope["public_key"], b"")
    assert len(empty_envelope["ciphertext"]) == 2 * (SM2_C1_BYTES + SM2_C3_BYTES)
    assert SM2Crypto.decrypt(private_key, empty_envelope) == b""
    # 但把非空密文砍到刚好 C1+C3，就会解出错误明文 → 必须被 C3 拦住
    truncated = dict(envelope, ciphertext=ct[: 2 * (SM2_C1_BYTES + SM2_C3_BYTES)])
    _expect_integrity_error(
        lambda: SM2Crypto.decrypt(private_key, truncated), "被截断成恰好 C1+C3 的密文"
    )


def test_kdf_degenerate_retries_with_fresh_k():
    """国标 §6.1 A5 的硬性要求：KDF 输出全零时**换一个 k 重来**（回 A1），不是照常输出。

    全零掩码实际概率是 2^-256，没法靠随机采样触发，所以这里把 `_kdf` 换成
    "第一次返回全零、之后走真实现"的探针，并让 `secrets.randbelow` 依次
    返回 k1、k2 —— 然后断言密文是用 k2 生成的（即真的重试了）。
    """
    fake_k1 = 0x1111
    fake_k2 = 0x2222
    real_kdf = sm2._kdf
    real_randbelow = sm2.secrets.randbelow
    calls = {"kdf": 0}

    def fake_kdf(z, klen):
        calls["kdf"] += 1
        if calls["kdf"] == 1:
            return b"\x00" * klen
        return real_kdf(z, klen)

    sequence = iter([fake_k1 - 1, fake_k2 - 1])
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = b"retry-me"

    try:
        sm2._kdf = fake_kdf
        sm2.secrets.randbelow = lambda n: next(sequence)
        envelope = SM2Crypto.encrypt(public_key, plaintext)
    finally:
        sm2._kdf = real_kdf
        sm2.secrets.randbelow = real_randbelow

    assert calls["kdf"] >= 2, "KDF 全零后没有重试"
    expected_c1 = sm2._point_to_hex(*sm2._base_mul(fake_k2, SM2_CURVE))
    assert envelope["ciphertext"][:130] == expected_c1, "重试后用的不是新的 k"
    # 重试路径产出的是正常信封，能正常解开
    assert SM2Crypto.decrypt(private_key, envelope) == plaintext


def test_test_k_hook_is_validated():
    """测试用的 k 也要过范围检查 —— 否则"测试后门"会变成生产漏洞。"""
    public_key = SM2Crypto.public_key_of(_fresh_scalar())
    for bad in (0, -1, SM2_N, SM2_N + 1, 1 << 300, "1", 1.5, True):
        try:
            SM2Crypto.encrypt(public_key, b"x", k=bad)
        except ValueError:
            continue
        raise AssertionError(f"k = {bad!r} 竟然被接受了")
    # 合法 k 必须稳定复现同一个密文（这正是它存在的意义）
    a = SM2Crypto.encrypt(public_key, b"x", k=0x1234)
    b = SM2Crypto.encrypt(public_key, b"x", k=0x1234)
    assert a == b


# ---------------------------------------------------------------------------
# 5. 独立性：不能只是"自己跟自己对得上"
# ---------------------------------------------------------------------------
#: 独立性检查的实际方式，供 _main 打印（"我们到底证明了什么"）
_INDEPENDENCE_MODE = "未运行"


def test_independence_gmssl_if_available():
    """如果环境里装了 `gmssl`（一个**独立实现**），做双向互通。

    * 本模块加密 → `gmssl` 解密（mode=1 即 C1C3C2）
    * `gmssl` 加密 → 本模块解密

    容器里没有 `gmssl`，所以这条通常会被跳过；跳过时**不打印 OK 冒充通过**。
    """
    global _INDEPENDENCE_MODE
    try:
        from gmssl import sm2 as gmssl_sm2  # type: ignore
    except ImportError:
        _INDEPENDENCE_MODE = (
            "容器内无 gmssl → 由「国标附录逐字节向量 + 第二条代码路径复算」兜底；"
            "另有**宿主上一次性 venv（gmssl 3.2.2）里跑过的双向互通 + 固定 k 逐字节等价**，"
            "见交付说明（那部分结果不随本次运行输出）"
        )
        print("         （gmssl 未安装，跳过互通；改由备选路径复算证明，见下）")
        return

    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = b"cross-implementation check"

    # 本模块 → gmssl（gmssl 的 mode=1 就是 C1C3C2，与本模块一致）
    envelope = SM2Crypto.encrypt(public_key, plaintext)
    peer = gmssl_sm2.CryptSM2(private_key=private_key, public_key=public_key, mode=1)
    assert peer.decrypt(bytes.fromhex(envelope["ciphertext"])) == plaintext, (
        "gmssl 解不开本模块的密文"
    )

    # gmssl → 本模块
    theirs = gmssl_sm2.CryptSM2(private_key=private_key, public_key=public_key, mode=1).encrypt(
        plaintext
    )
    assert SM2Crypto.decrypt(private_key, {"ciphertext": theirs.hex()}) == plaintext, (
        "本模块解不开 gmssl 的密文"
    )
    _INDEPENDENCE_MODE = "gmssl 双向互通（真·独立实现交叉验证）"


def test_independence_second_path():
    """第二套换算路径：**不复用 `_point_mul` 的滑动窗口结构**，用教科书式的
    逐比特 double-and-add（每次加倍 + 按比特决定是否加点）重算共享点，
    再独立地重建 KDF 与 C3，最后与 `decrypt` 的结果对比。

    若加密端把 k、点乘、KDF、C3 里的任何一环写错，两条路径不会同时"错得一样"。

    **它证明什么 / 不证明什么**：
    * 证明：解密结果不是被某一处实现的 bug 凑出来的，两个结构不同的算法给出一致结果；
    * 不证明：与外部实现的互操作性 —— 那要靠上面的国标附录向量（逐字节对齐国标原文）
      与（若可用）`gmssl` 互通。这一点必须说清楚，不能拿自洽当互通。
    """
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = os.urandom(48)
    envelope = SM2Crypto.encrypt(public_key, plaintext)

    ct = bytes.fromhex(envelope["ciphertext"])
    c1_hex = ct[:SM2_C1_BYTES].hex()
    c3 = ct[SM2_C1_BYTES:SM2_C1_BYTES + SM2_C3_BYTES]
    c2 = ct[SM2_C1_BYTES + SM2_C3_BYTES:]

    # --- 教科书式仿射 double-and-add，与本模块的 Jacobian 滑动窗口完全不同的控制流 ---
    # 注意：曲线参数必须**作为入参传进来**，不能写死成 SM2_P / SM2_A。
    # 国标附录 A.2 示例2 用的是它自己的一条测试曲线（GB_CURVE），
    # 若这里仍按生产曲线取模，算出的 [d_B]C1 必然对不上国标给的 (x2, y2) ——
    # 那是**测试自己的写法错误**，不是密码学实现的问题。
    def affine_add(p1, p2, p, a):
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        x1, y1 = p1
        x2, y2 = p2
        if x1 == x2 and (y1 + y2) % p == 0:
            return None
        if x1 == x2 and y1 == y2:
            lam = (3 * x1 * x1 + a) * pow(2 * y1, -1, p) % p
        else:
            lam = (y2 - y1) * pow(x2 - x1, -1, p) % p
        x3 = (lam * lam - x1 - x2) % p
        return x3, (lam * (x1 - x3) - y1) % p

    def affine_mul(scalar, point, p, a):
        result = None
        addend = point
        while scalar:
            if scalar & 1:
                result = affine_add(result, addend, p, a)
            addend = affine_add(addend, addend, p, a)
            scalar >>= 1
        return result

    d = int(private_key, 16)
    shared = affine_mul(d, (int(c1_hex[2:66], 16), int(c1_hex[66:], 16)), SM2_P, SM2_A)
    assert shared is not None
    x2, y2 = shared

    # 独立重建 KDF（不复用 _kdf）
    stream = b""
    counter = 1
    while len(stream) < len(c2):
        stream += sm3_digest(x2.to_bytes(32, "big") + y2.to_bytes(32, "big") + struct.pack(">I", counter))
        counter += 1
    recovered = bytes(a ^ b for a, b in zip(c2, stream[: len(c2)]))
    assert recovered == plaintext, "第二条路径解出的明文与 encrypt 的输入不一致"
    assert (
        sm3_digest(x2.to_bytes(32, "big") + recovered + y2.to_bytes(32, "big")) == c3
    ), "第二条路径算出的 C3 与密文里的 C3 不一致"
    assert SM2Crypto.decrypt(private_key, envelope) == recovered

    # 同一套独立路径再打一遍国标向量，确认它不是"和新实现一起错"。
    # 注意：这里必须拿 **hex 字符串** 切片（C1 是 130 个 hex 字符）；
    # 先把 ciphertext 转成 bytes 再切 [:130] 会切成前 130 **字节**，
    # 那已经不是 C1 了 —— 这个坑我踩过一次，留注释在这里。
    gb_env = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)
    gb_ct = gb_env["ciphertext"]
    gb_shared = affine_mul(
        int(GB_DB, 16), (int(GB_C1[2:66], 16), int(GB_C1[66:], 16)), GB_CURVE.p, GB_CURVE.a
    )
    assert gb_shared == (int(GB_X2, 16), int(GB_Y2, 16)), "独立路径算出的 [d_B]C1 与国标不符"
    assert gb_ct[:130] == GB_C1.lower(), "独立路径跑出来的国标 C1 不符"
    assert gb_ct == (GB_C1 + GB_C3 + GB_C2).lower(), "独立路径跑出来的国标密文不符"
    assert len(bytes.fromhex(gb_ct)) == SM2_C1_BYTES + SM2_C3_BYTES + len(GB_M)

    # 顺带把 `k=` 钩子钉成"无状态"：同一个 k 反复用、以及被别的加密夹在中间，
    # 都必须稳定复现同一段 C1。否则它就是"会悄悄退化成随机 k"的坑，
    # 而这种失败看起来会像密码学 bug（这正是它该被显式验证的原因）。
    first = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)["ciphertext"]
    SM2Crypto.encrypt(SM2Crypto.public_key_of(_fresh_scalar()), os.urandom(16))
    SM2Crypto.encrypt(GB_PB, b"another message", k=GB_K, curve=GB_CURVE)
    again = SM2Crypto.encrypt(GB_PB, GB_M, k=GB_K, curve=GB_CURVE)["ciphertext"]
    assert first == again, "k= 钩子不是纯函数：同样的 k 两次得到不同密文"

    global _INDEPENDENCE_MODE
    if "gmssl" not in _INDEPENDENCE_MODE:
        _INDEPENDENCE_MODE = (
            "第二条代码路径（仿射 double-and-add + 独立 KDF/C3）复算一致 —— "
            + _INDEPENDENCE_MODE
        )


# ---------------------------------------------------------------------------
# 6. 随机性
# ---------------------------------------------------------------------------
def test_each_encryption_uses_fresh_k():
    """同一公钥、同一明文两次加密的 C1 必须不同（否则 k 复用 ⇒ 私钥可解）。"""
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = b"same plaintext"

    c1s = set()
    c3s = set()
    for _ in range(8):
        envelope = SM2Crypto.encrypt(public_key, plaintext)
        ct = envelope["ciphertext"]
        c1s.add(ct[:130])
        c3s.add(ct[130:194])
        assert SM2Crypto.decrypt(private_key, envelope) == plaintext
    assert len(c1s) == 8, f"8 次加密只出现了 {len(c1s)} 种 C1 —— k 没有随机化"
    assert len(c3s) == 8, "C3 出现重复 —— 随机数质量有问题"


def test_random_k_is_uniform_ish_over_range():
    """抽查 `_pick_k` 的值域：必须落在 [1, n-1]，且高位有变化（不是小常数）。"""
    values = [sm2._pick_k() for _ in range(64)]
    assert all(1 <= v <= SM2_N - 1 for v in values), "k 超出 [1, n-1]"
    assert len(set(values)) == 64, "64 次取样出现重复，随机源有问题"
    assert max(values) > (1 << 200), "k 的值域明显偏小"


# ---------------------------------------------------------------------------
# 7. 性能（纯 Python 大整数运算，如实记录量级）
# ---------------------------------------------------------------------------
def test_performance_rough():
    """32 字节载荷的加/解密耗时 —— 打印实测值，并给一个宽松的上限。

    分派是低频操作，这里只是**如实记录**量级，不是性能门禁。
    """
    private_key = _fresh_scalar()
    public_key = SM2Crypto.public_key_of(private_key)
    plaintext = os.urandom(32)
    rounds = 10

    start = time.perf_counter()
    for _ in range(rounds):
        envelope = SM2Crypto.encrypt(public_key, plaintext)
    encrypt_ms = (time.perf_counter() - start) / rounds * 1000

    start = time.perf_counter()
    for _ in range(rounds):
        SM2Crypto.decrypt(private_key, envelope)
    decrypt_ms = (time.perf_counter() - start) / rounds * 1000

    print(f"         32B 载荷：encrypt {encrypt_ms:.2f} ms/op，decrypt {decrypt_ms:.2f} ms/op")
    assert encrypt_ms < _SLOW_OP_MS, f"加密 {encrypt_ms:.1f} ms 超出预期上限"
    assert decrypt_ms < _SLOW_OP_MS, f"解密 {decrypt_ms:.1f} ms 超出预期上限"


# ---------------------------------------------------------------------------
# 自运行入口（不依赖 pytest）
# ---------------------------------------------------------------------------
def _main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failed = []
    print(f"== SM2 自测：{len(tests)} 项 ==\n")
    for name, fn in tests:
        start = time.perf_counter()
        try:
            fn()
        except Exception as exc:
            failed.append((name, exc))
            print(f"  [FAIL] {name}\n         {type(exc).__name__}: {exc}")
        else:
            print(f"  [OK]   {name}  ({(time.perf_counter() - start) * 1000:.0f} ms)")
    print(f"\n== 独立性检查实际方式：{_INDEPENDENCE_MODE}")
    print(f"== 结果：{len(tests) - len(failed)} 通过 / {len(failed)} 失败 ==")
    if failed:
        for name, exc in failed:
            print(f"  失败项 {name}: {exc}")
        return 1
    print("SM2 公钥加密通过国标标准向量、失败路径区分与随机性检查。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
