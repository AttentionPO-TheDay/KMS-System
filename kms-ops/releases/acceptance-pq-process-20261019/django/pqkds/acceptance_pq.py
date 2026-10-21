"""Bounded native algorithm checks using ONLY ephemeral/public test material.

No models, registry, business key store, chain calls or algorithm fallbacks.
Uses the same KyberCrypto/FalconCrypto wrappers as the deployed application.
"""
import ctypes
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

CASES = {
    'pq-parameter-downgrade': 'KYBER 密文篡改',
    'pq-sign-encrypt-confusion': 'FALCON 消息篡改',
    'pq-secret-upload': 'KYBER 错误私钥替换',
    'pq-issuance-source-forgery': 'FALCON 签名篡改与公钥替换',
}


def run_checks(case_id):
    if case_id not in CASES:
        raise ValueError('Unknown fixed algorithm case')
    from .crypto_utils import KyberCrypto, FalconCrypto
    vectors = json.loads(Path(__file__).with_name('acceptance_pq_vectors.json').read_text())
    evidence = {
        'version': 1, 'caseId': case_id, 'category': CASES[case_id],
        'source': '已部署 crypto_utils.KyberCrypto / FalconCrypto 原生库；独立 JS 实现互操作向量 v1',
        'scope': 'KYBER round-3（512/768/1024）、FALCON-512 的功能与负向验证；不等同于 ML-KEM/FIPS 认证或量子攻击实测。',
        'checks': [], 'passed': False,
    }

    def check(check_id, name, expected, operation, success_text, failure_text):
        started = perf_counter()
        # Exceptions are execution errors, NEVER counted as rejection success.
        try:
            passed = bool(operation())
            actual = success_text if passed else failure_text
            state = 'passed' if passed else 'failed'
        except Exception:
            passed, actual, state = False, '算法执行异常，未获得判定证据', 'error'
        evidence['checks'].append({
            'id': check_id, 'name': name, 'expected': expected, 'actual': actual,
            'passed': passed, 'status': state,
            'durationMs': round((perf_counter() - started) * 1000, 3),
            'recordedAt': datetime.now(timezone.utc).isoformat(),
        })

    if case_id.startswith('pq-') and case_id in ('pq-parameter-downgrade', 'pq-secret-upload'):
        for vector in vectors['kyber']:
            variant = vector['variant']
            crypto = KyberCrypto(variant)
            # Keys are local to this invocation. No registry/cache/DB writes.
            pk, sk = crypto.generate_keypair()
            ct, shared = crypto.encrypt(pk)
            prefix = str(variant) + '-'
            check(prefix + 'roundtrip', f'KYBER-{variant} 正常封装/解封装',
                  '正常双方共享密钥逐字节一致（32字节）',
                  lambda: len(shared) == 32 and hmac.compare_digest(crypto.decrypt(ct, sk), shared),
                  '32字节共享密钥一致', '正常共享密钥不一致')
            if case_id == 'pq-parameter-downgrade':
                def kat():
                    u8 = ctypes.c_ubyte
                    public = (u8 * crypto.public_key_bytes)()
                    secret = (u8 * crypto.secret_key_bytes)()
                    seed = (u8 * 64).from_buffer_copy(bytes.fromhex(vectors['seedHex']))
                    fn = getattr(crypto.dll, f'pqcrystals_kyber{variant}_ref_keypair_derand')
                    fn.argtypes = [ctypes.POINTER(u8)] * 3
                    fn.restype = ctypes.c_int
                    try:
                        return (fn(public, secret, seed) == 0
                                and hashlib.sha256(bytes(public)).hexdigest() == vector['pkSha256']
                                and hashlib.sha256(bytes(secret)).hexdigest() == vector['skSha256']
                                and hmac.compare_digest(
                                    crypto.decrypt(bytes.fromhex(vector['ciphertextHex']), bytes(secret)),
                                    bytes.fromhex(vector['sharedSecretHex'])))
                    finally:
                        ctypes.memset(secret, 0, ctypes.sizeof(secret))
                check(prefix + 'interop', f'KYBER-{variant} 固定向量与独立 JS 互操作',
                      '固定公开测试种子生成结果匹配冻结向量，并能解封装独立 JS 密文', kat,
                      '公私钥测试摘要匹配，独立 JS 密文解封装一致', '固定向量或独立 JS 互操作不匹配')
                damaged = bytearray(ct)
                damaged[0] ^= 1
                check(prefix + 'tamper', f'KYBER-{variant} 密文首字节翻转1位',
                      '隐式拒绝：返回32字节替代值，与原共享密钥不同',
                      lambda: len(crypto.decrypt(bytes(damaged), sk)) == 32
                      and not hmac.compare_digest(crypto.decrypt(bytes(damaged), sk), shared),
                      '得到32字节替代值，与原共享密钥不同，隐式拒绝生效', '篡改密文仍恢复原共享密钥或结果长度异常')
            else:
                other_pk, other_sk = crypto.generate_keypair()
                other_ct, other_shared = crypto.encrypt(other_pk)
                check(prefix + 'other-control', f'KYBER-{variant} 第二套临时密钥正常对照',
                      '独立生成的公钥不同，第二套密钥自己的封装可正常还原',
                      lambda: pk != other_pk and len(other_shared) == 32
                      and hmac.compare_digest(crypto.decrypt(other_ct, other_sk), other_shared),
                      '两套公钥不同，第二套正常封装可还原', '独立密钥或正常对照异常')
                check(prefix + 'wrong-key', f'KYBER-{variant} 替换为第二套临时私钥',
                      '错误私钥不能恢复第一套共享密钥',
                      lambda: len(crypto.decrypt(ct, other_sk)) == 32
                      and not hmac.compare_digest(crypto.decrypt(ct, other_sk), shared),
                      '错误私钥产生不同共享密钥，跨密钥隔离生效', '错误私钥仍恢复原共享密钥或结果长度异常')
    else:
        crypto = FalconCrypto(512)
        pk, sk = crypto.generate_keypair()
        message = b'KMS acceptance ephemeral message v1'
        signed = crypto.sign(message, sk)
        check('falcon-roundtrip', 'FALCON-512 正常签名/验签', '正常签名验证成功并还原原消息',
              lambda: crypto.verify(signed, pk) == message, '正常签名验签成功，消息一致', '正常签名未能验证')
        vector = vectors['falcon']
        check('falcon-interop', 'FALCON-512 独立 JS 签名互操作',
              '部署原生库能验证 @noble/post-quantum 生成的公开测试签名',
              lambda: crypto.verify(bytes.fromhex(vector['signedMessageHex']), bytes.fromhex(vector['publicKeyHex']))
              == bytes.fromhex(vector['messageHex']),
              '独立 JS 签名验签成功，消息一致', '独立 JS 签名无法验证或消息不符')
        if case_id == 'pq-sign-encrypt-confusion':
            # Attached format contains nonce + message + signature. Locate the actual message.
            position = signed.find(message)
            if position < 0:
                raise RuntimeError('Attached signed message format unavailable')
            damaged = bytearray(signed)
            damaged[position] ^= 1
            check('falcon-message-tamper', 'FALCON-512 仅修改消息内容', '保留签名，修改消息后必须验签失败',
                  lambda: crypto.verify(bytes(damaged), pk) is None,
                  '消息翻转1位后原生验签返回拒绝', '修改消息后仍被验签接受')
        else:
            damaged = bytearray(signed)
            damaged[-1] ^= 1
            check('falcon-signature-tamper', 'FALCON-512 修改签名末字节', '保持消息不变，修改签名后必须验签失败',
                  lambda: crypto.verify(bytes(damaged), pk) is None,
                  '签名翻转1位后原生验签返回拒绝', '修改签名后仍被验签接受')
            other_pk, other_sk = crypto.generate_keypair()
            check('falcon-other-control', 'FALCON-512 第二套临时密钥正常对照', '独立公钥不同，第二套签名可正常验签',
                  lambda: pk != other_pk and crypto.verify(crypto.sign(message, other_sk), other_pk) == message,
                  '两套公钥不同，第二套正常验签成功', '独立密钥或正常验签异常')
            check('falcon-wrong-key', 'FALCON-512 替换验签公钥', '第一套签名使用第二套公钥必须验签失败',
                  lambda: crypto.verify(signed, other_pk) is None,
                  '错误公钥不能通过原签名的验签', '错误公钥仍能通过原签名验签')
    evidence['passed'] = bool(evidence['checks']) and all(row['passed'] for row in evidence['checks'])
    return evidence
