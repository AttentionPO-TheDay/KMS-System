# -*- coding: utf-8 -*-
"""生成"服务端封、浏览器解"的互通样本（P3 收尾验收用）。

为什么需要它
------------
国标向量证明了两侧实现**各自**是对的，但用户实际遇到的是**跨实现**的场景：
服务端用 Python 的 `sm2_crypto` 封装，浏览器用 JS 的 `sm2-envelope` 解开。
两边只要有一处细节不同（比如 C1 的长度、KDF 的计数器字节序、C3 的拼接顺序），
国标向量那两条断言都照样通过，而用户就是解不开。

所以这一条是"用户能不能真解开"的最后一道关。

用法：docker exec -w /backend dvadmin3-django python /tmp/make_sm2_interop_sample.py /tmp/interop.json
"""

import json
import secrets
import sys

sys.path.insert(0, '/backend')

from pqkds.sm2_crypto import SM2Crypto  # noqa: E402

SM2_N = int('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/interop.json'

    # 用户侧私钥 d_A 与对应公钥 P_A（服务端就是封给 P_A 的）
    d_a = secrets.randbelow(SM2_N - 1) + 1
    d_a_hex = format(d_a, '064x')
    p_a_hex = SM2Crypto.public_key_of(d_a_hex)

    # 要封的东西：一把 SM4 载荷密钥（16 字节 → 32 位十六进制）
    payload_key = secrets.token_bytes(16)
    expected_hex = payload_key.hex()

    envelope = SM2Crypto.encrypt(p_a_hex, payload_key)

    sample = {
        'privateKey': d_a_hex,
        'publicKey': p_a_hex,
        'expectedKeyHex': expected_hex,
        'envelope': envelope,
    }
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(sample, fh, ensure_ascii=False, indent=2)

    # 自检：服务端自己能解开（否则样本本身就是坏的，测出来的失败会指向错误的方向）
    back = SM2Crypto.decrypt(d_a_hex, envelope)
    assert back == payload_key, '服务端自解不一致，样本无效'
    print('样本已写出: %s' % out_path)
    print('  密文长度 %d 字符（C1 130 + C3 64 + C2 %d）'
          % (len(envelope['ciphertext']), len(envelope['ciphertext']) - 194))
    print('  服务端自解: OK')


if __name__ == '__main__':
    main()
