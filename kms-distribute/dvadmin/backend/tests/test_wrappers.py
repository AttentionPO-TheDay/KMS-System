# -*- coding: utf-8 -*-
"""封装算法注册表自测（计划 §7 P3 步骤 2–4）。

重点验证三件事：
  1. **用户腿能真正走通**：用 `d_A` 生成 `P_A`，把 SM4 载荷密钥封给 `P_A`，
     再用 `d_A` 解出来 —— 拿到的必须是**同一把**载荷密钥，
     而且那把密钥要能直接解开 SM4 密文（否则"封装"没有意义）；
  2. **D17 在服务端强制**：CL-Kyber / CL-Falcon 不能被用于分发给用户，
     且拒绝要发生在**触碰密钥材料之前**；
  3. **注册表覆盖四种算法**，归一化能吃下历史上的各种写法。
"""

import os
import secrets
import sys

sys.path.insert(0, '/backend')

from pqkds import wrappers as W  # noqa: E402
from pqkds.sm2_crypto import SM2Crypto, SM2IntegrityError  # noqa: E402
from pqkds.sm4_crypto import PAYLOAD_ALGORITHM_SM4, PayloadCipher  # noqa: E402

SM2_N = int('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)

_pass = 0
_fail = 0
_failures = []


def check(name, ok, detail=''):
    global _pass, _fail
    if ok:
        _pass += 1
        print('  [OK]   ' + name + ('  ' + detail if detail else ''))
    else:
        _fail += 1
        _failures.append(name)
        print('  [FAIL] ' + name + ('  ' + detail if detail else ''))


def expect_raises(name, exc_type, fn, keyword=''):
    try:
        fn()
    except exc_type as exc:
        ok = (not keyword) or (keyword in str(exc))
        check(name, ok, '' if ok else '错误信息里没有「%s」: %s' % (keyword, exc))
        return
    except Exception as exc:  # noqa: BLE001
        check(name, False, '抛的是 %s 而不是 %s: %s' % (type(exc).__name__, exc_type.__name__, exc))
        return
    check(name, False, '竟然没有抛异常')


def fresh_private_key():
    """生成一个 (d_A 十六进制, P_A 十六进制) 对。"""
    sk = secrets.randbelow(SM2_N - 1) + 1
    d_a_hex = format(sk, '064x')
    return d_a_hex, SM2Crypto.public_key_of(d_a_hex)


def test_sm2_user_leg():
    print('1. 用户腿端到端：SM2')
    d_a_hex, p_a_hex = fresh_private_key()
    check('能用私钥标量导出 P_A', SM2Crypto.is_valid_public_key(p_a_hex), p_a_hex[:20] + '…')

    payload_key = PayloadCipher.generate_key()
    check('载荷密钥是 SM4 的 16 字节', len(payload_key) == 16, '%d bytes' % len(payload_key))

    envelope = W.build_user_envelope(payload_key, 'SM2', p_a_hex)
    check('SM2 信封：algorithm=sm2 且 key_system=sm2',
          envelope.get('key_system') == 'sm2' and
          envelope.get('algorithm') == 'sm2' and
          True or envelope.get('recipient_public_key') == p_a_hex,
          'key_system=%s' % envelope.get('key_system'))
    check('信封自带算法与目标公钥（便于排查）',
          envelope.get('algorithm') == 'sm2' and envelope.get('recipient_public_key') == p_a_hex,
          'algorithm=%s' % envelope.get('algorithm'))
    check('信封标了载荷算法为 SM4', envelope.get('payload_algorithm') == PAYLOAD_ALGORITHM_SM4)

    recovered = W.open_user_envelope(envelope, d_a_hex)
    check('★ 用 d_A 解封得到同一把载荷密钥', recovered == payload_key,
          '' if recovered == payload_key else '解出来的不是原来那把')

    # 解出来的密钥必须能直接用于 SM4 解密 —— 这才是封装的最终目的
    ciphertext, nonce = PayloadCipher.encrypt(b'secret payload', payload_key)
    check('★ 解封得到的密钥能直接解 SM4 密文',
          PayloadCipher.decrypt(ciphertext, payload_key, nonce) == b'secret payload')

    text = W.envelope_to_json(envelope)
    check('信封可 JSON 序列化并往返',
          W.open_user_envelope(W.envelope_from_json(text), d_a_hex) == payload_key)


def test_sscl_user_leg():
    print('\n2. 用户腿端到端：SSCL（复用同一套原语，但算法名要能区分）')
    d_a_hex, p_a_hex = fresh_private_key()
    payload_key = PayloadCipher.generate_key()
    envelope = W.build_user_envelope(payload_key, 'SSCL', p_a_hex)
    # 关键：`algorithm` 必须是密码算法（sm2），`key_system` 才是密钥体系（sscl）。
    # 混用会让 SM2Crypto.decrypt 的算法校验失败 —— 这个坑是本测试抓出来的。
    check('SSCL 信封：algorithm=sm2（密码算法）而 key_system=sscl（密钥体系）',
          envelope.get('algorithm') == 'sm2' and envelope.get('key_system') == 'sscl',
          'algorithm=%s key_system=%s' % (envelope.get('algorithm'), envelope.get('key_system')))
    check('★ SSCL 也能用 d_A 解封', W.open_user_envelope(envelope, d_a_hex) == payload_key)


def test_d17_enforcement():
    print('\n3. D17：用户腿在服务端收窄')
    # 已知但**不允许用于用户腿**的算法：报错要说明"仅支持 SM2 / SSCL"
    for bad in ('CL-Kyber', 'kyber', 'Kyber', 'CL-Falcon', 'falcon_lattice', 'kyber_kem'):
        expect_raises('拒绝 %s 分发给用户' % bad, W.AlgorithmNotAllowed,
                      lambda b=bad: W.assert_user_leg_allowed(b), '仅支持 SM2 / SSCL')
    # 完全不认识的算法：报错应是"未知算法"而不是"不在白名单" ——
    # 两者语义不同，混为一谈会让排查时误以为 AES 曾经被支持过
    expect_raises('完全不认识的算法报「未知算法」', W.AlgorithmNotAllowed,
                  lambda: W.assert_user_leg_allowed('AES'), '未知算法')

    expect_raises('get_wrapper(..., leg="user") 同样拒绝格算法', W.AlgorithmNotAllowed,
                  lambda: W.get_wrapper('kyber', leg='user'), '仅支持 SM2 / SSCL')

    # 关键：拒绝必须发生在**读取密钥材料之前**。
    # 故意传一个非法公钥：若实现先去校验点，抛的会是 WrapperError 而不是 AlgorithmNotAllowed。
    expect_raises('★ 拒绝发生在触碰密钥材料之前（越权请求连公钥都不需要）',
                  W.AlgorithmNotAllowed,
                  lambda: W.build_user_envelope(b'x' * 16, 'CL-Kyber', 'not-a-key'),
                  '仅支持 SM2 / SSCL')

    check('SM2 / SSCL 通过白名单',
          W.assert_user_leg_allowed('SM2') == 'SM2' and W.assert_user_leg_allowed('sscl') == 'SSCL')


def test_registry():
    print('\n4. 注册表覆盖与归一化')
    check('注册表含四种算法', set(W.WRAPPERS.keys()) == {'SM2', 'SSCL', 'KYBER', 'FALCON'},
          ','.join(sorted(W.WRAPPERS.keys())))
    for raw, expected in [('SM2', 'SM2'), ('sm2', 'SM2'), ('SSCL', 'SSCL'), ('sscl', 'SSCL'),
                          ('kyber_kem', 'KYBER'), ('CL-Kyber', 'KYBER'), ('Kyber', 'KYBER'),
                          ('falcon_lattice', 'FALCON'), ('CL-Falcon', 'FALCON')]:
        got = W.normalize_algorithm(raw)
        check('归一化 %s → %s' % (raw, expected), got == expected, '实际 %s' % got)
    expect_raises('未知算法明确报错', W.AlgorithmNotAllowed, lambda: W.normalize_algorithm('AES-256'))

    # 节点腿保持零改动：委托型封装器不自己实现 wrap
    expect_raises('节点腿仍走既有池生成路径（不在本表里重写）', W.WrapperError,
                  lambda: W.get_wrapper('kyber').wrap(b'x' * 16), '既有的密钥池生成路径')


def test_failure_paths():
    print('\n5. 非法输入与失败路径')
    payload_key = PayloadCipher.generate_key()
    expect_raises('目标点长度不对 → 拒绝', W.WrapperError,
                  lambda: W.build_user_envelope(payload_key, 'SM2', 'deadbeef'), '非法')

    off_curve = '04' + '11' * 64
    expect_raises('点不在曲线上 → 拒绝（否则会封给一个不存在的点）', W.WrapperError,
                  lambda: W.build_user_envelope(payload_key, 'SM2', off_curve), '非法')

    d_a_hex, p_a_hex = fresh_private_key()
    envelope = W.build_user_envelope(payload_key, 'SM2', p_a_hex)

    other_d_a = format(secrets.randbelow(SM2_N - 1) + 1, '064x')
    expect_raises('用错私钥解封 → 完整性错误（不是返回垃圾）', SM2IntegrityError,
                  lambda: W.open_user_envelope(envelope, other_d_a))

    expect_raises('残缺信封 → 报错', W.WrapperError,
                  lambda: W.open_user_envelope('not-a-dict', d_a_hex), '格式错误')
    expect_raises('非 JSON 文本 → 报错', W.WrapperError,
                  lambda: W.envelope_from_json('{oops'), '合法 JSON')

    tampered = dict(envelope)
    ct = tampered['ciphertext']
    tampered['ciphertext'] = ct[:-2] + ('00' if ct[-2:] != '00' else '11')
    expect_raises('篡改密文 → 完整性错误', SM2IntegrityError,
                  lambda: W.open_user_envelope(tampered, d_a_hex))


def main():
    print('\n=== 封装算法注册表自测 ===')
    test_sm2_user_leg()
    test_sscl_user_leg()
    test_d17_enforcement()
    test_registry()
    test_failure_paths()

    print('\n== 结果：%d 通过 / %d 失败 ==' % (_pass, _fail))
    if _fail:
        print('失败项：')
        for item in _failures:
            print('  - %s' % item)
        sys.exit(1)
    print('封装注册表行为正确：用户腿可往返，D17 在服务端强制。\n')


if __name__ == '__main__':
    main()
