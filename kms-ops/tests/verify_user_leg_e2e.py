# -*- coding: utf-8 -*-
"""用户腿分发端到端验收（P3 的收口验证）。

这是整条链路唯一有意义的终极断言：
    **分发给用户的信封，用户能用自己的 `d_A` 解开，且解出来的就是那把 SM4 密钥。**

它把下列各环节串起来，任何一环接错都会在这里暴露：

    KMS 自省拿身份 → 校验节点授权 → 取 P_A（= d_A·G，非 W_A）
      → 生成 SM4 载荷密钥 → 用 P_A 封装 → 落库
      → 用户取回信封 → 用 d_A 解封 → 哈希与库中记录一致

为什么在容器里跑
----------------
解封需要 SM3 与椭圆曲线运算。容器里已有经过国标向量验证的 `pqkds/sm2_crypto.py`，
直接复用它比在 Node 里再造一份 SM3 可靠得多 —— 而且这样验的是**真正上线的那份实现**。

用法（在 dvadmin3-django 容器内）：
    docker exec -w /backend dvadmin3-django python /tmp/verify_user_leg_e2e.py
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import time

import requests

sys.path.insert(0, '/backend')

from pqkds.sm2_crypto import SM2Crypto  # noqa: E402

GATEWAY = os.environ.get('E2E_GATEWAY', 'http://nginx')
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


def main():
    print('\n=== 用户腿分发端到端验收 ===\n')

    # -----------------------------------------------------------------------
    print('1. 登录并生成一对**已知**的本地份额 (u, uA)')
    login = requests.post(
        f'{GATEWAY}/lifecycle-api/login',
        json={'username': 'yx', 'password': 'admin123'}, timeout=15,
    ).json()
    token = login.get('token')
    if not token:
        print('  登录失败，无法继续')
        sys.exit(1)
    auth = {'Authorization': 'Bearer ' + token}

    u = secrets.randbelow(SM2_N - 1) + 1
    u_hex = format(u, '064x')
    ua = SM2Crypto.public_key_of(u_hex)
    print('  u 已生成（%d 位十六进制），其公钥 uA=%s…' % (len(u_hex), ua[:18]))

    # -----------------------------------------------------------------------
    print('\n2. 登记这把 SM2 密钥')
    key_name = 'e2e-用户腿-%d' % int(time.time())
    created = requests.post(
        f'{GATEWAY}/generate-api/generate/keymanage',
        headers={**auth, 'Content-Type': 'application/json'},
        json={
            'encrytType': '无证书非对称加密', 'encrytName': 'SM2',
            'keyName': key_name, 'keyUse': 'E2E 验收', 'keyDomain': 'A', 'uA': ua,
        }, timeout=20,
    ).json()
    check('登记请求已受理', created.get('code') == 200, 'code=%s' % created.get('code'))

    key_id = None
    for _ in range(30):
        rows = requests.get(
            f'{GATEWAY}/generate-api/generate/key/list?pageSize=200',
            headers=auth, timeout=20,
        ).json().get('rows') or []
        hit = [r for r in rows if r.get('keyName') == key_name]
        if hit:
            key_id = hit[0]['keyId']
            break
        time.sleep(0.7)
    check('密钥已入库（Kafka 异步落库完成）', key_id is not None, 'keyId=%s' % key_id)
    if key_id is None:
        print('\n没有 keyId，无法继续')
        sys.exit(1)

    # -----------------------------------------------------------------------
    print('\n3. 取回 t_A 并算出 d_A = (t_A + u) mod n')
    detail = requests.get(
        f'{GATEWAY}/lifecycle-api/lifecycle/keymanage/{key_id}',
        headers=auth, timeout=20,
    ).json().get('data') or {}
    material = detail.get('key_value') or detail.get('keyValue')
    if isinstance(material, str):
        material = json.loads(material)
    t_a = material.get('partialKey')
    check('拿到 KMS 分片 t_A', bool(t_a), 't_A=%s…' % str(t_a)[:16])
    if not t_a:
        sys.exit(1)

    d_a = (int(t_a, 16) + u) % SM2_N
    d_a_hex = format(d_a, '064x')
    # 自检：d_A·G 必须等于 uA 之外的另一个点（不是 uA 本身，也不是 W_A）
    p_a = SM2Crypto.public_key_of(d_a_hex)
    check('d_A 是本机可用的私钥标量（能导出对应公钥）', SM2Crypto.is_valid_public_key(p_a), p_a[:18] + '…')

    # -----------------------------------------------------------------------
    print('\n4. 通过分发接口把对称密钥发给我自己')
    nodes = requests.get(f'{GATEWAY}/pqkds-api/user-nodes/', headers=auth, timeout=20).json().get('data') or {}
    node_list = nodes.get('nodes') or []
    check('能列出我被授权的节点', len(node_list) > 0,
          '节点=%s' % [n['nodeCode'] for n in node_list])
    if not node_list:
        sys.exit(1)
    node_ids = [n['nodeId'] for n in node_list[:2]]

    dist = requests.post(
        f'{GATEWAY}/pqkds-api/key-pool/distribute-to-user/',
        headers={**auth, 'Content-Type': 'application/json'},
        json={'source_key_id': key_id, 'node_ids': node_ids, 'count': 2}, timeout=60,
    ).json()
    data = dist.get('data') or {}
    check('分发成功返回批次号', bool(data.get('batchId')), 'batch=%s' % data.get('batchId'))
    check('★ 服务端回显的加密目标点 == 我算出的 d_A·G（证明封的是我能解的点）',
          str(data.get('recipientPublicKey', '')).lower() == p_a.lower(),
          '' if str(data.get('recipientPublicKey', '')).lower() == p_a.lower()
          else '回显=%s… 期望=%s…' % (str(data.get('recipientPublicKey'))[:18], p_a[:18]))
    check('为用户生成了信封', (data.get('userEnvelopeCount') or 0) >= 1,
          'userEnvelopes=%s' % data.get('userEnvelopeCount'))

    # -----------------------------------------------------------------------
    print('\n5. ★ 用 d_A 解封取回的对称密钥信封')
    keys = requests.get(f'{GATEWAY}/pqkds-api/user-symmetric-keys/', headers=auth, timeout=20).json().get('data') or {}
    items = [k for k in (keys.get('items') or []) if k.get('sourceKeyId') == key_id]
    check('「对称密钥查看」里能看到刚分发的信封', len(items) >= 1, '条数=%d' % len(items))
    if not items:
        sys.exit(1)

    opened = 0
    for item in items:
        one = requests.get(
            f'{GATEWAY}/pqkds-api/user-symmetric-keys/{item["id"]}/', headers=auth, timeout=20,
        ).json().get('data') or {}
        envelope = one.get('encryptedKeyData')
        if not envelope:
            continue
        envelope = json.loads(envelope) if isinstance(envelope, str) else envelope

        try:
            payload_key = SM2Crypto.decrypt(d_a_hex, envelope)
        except Exception as exc:  # noqa: BLE001
            check('解封信封 #%s' % item['id'], False, '%s: %s' % (type(exc).__name__, exc))
            continue

        digest = hashlib.sha256(payload_key).hexdigest()
        check('★ 解封信封 #%s：密钥哈希与库中记录一致（说明解出来的正是那把密钥）' % item['id'],
              digest == item.get('keyHash'),
              'SM4 密钥 %d 字节' % len(payload_key) if digest == item.get('keyHash')
              else '算出 %s… 库中 %s…' % (digest[:16], str(item.get('keyHash'))[:16]))
        check('  解出来的载荷密钥是 SM4 的 16 字节', len(payload_key) == 16, '%d 字节' % len(payload_key))
        opened += 1

    check('至少成功解封一份', opened >= 1, '成功 %d 份' % opened)

    # -----------------------------------------------------------------------
    print('\n6. 反向验证：拿**别的**私钥解不开（否则等于没加密）')
    other_d_a = format(secrets.randbelow(SM2_N - 1) + 1, '064x')
    one = requests.get(
        f'{GATEWAY}/pqkds-api/user-symmetric-keys/{items[0]["id"]}/', headers=auth, timeout=20,
    ).json().get('data') or {}
    envelope = json.loads(one['encryptedKeyData'])
    try:
        leaked = SM2Crypto.decrypt(other_d_a, envelope)
        check('用陌生私钥解封必须失败', False, '竟然解出了 %d 字节' % len(leaked))
    except Exception:
        check('用陌生私钥解封失败（信封确实只对 d_A 开放）', True)

    print('\n== 结果：%d 通过 / %d 失败 ==' % (_pass, _fail))
    if _fail:
        print('失败项：')
        for item in _failures:
            print('  - %s' % item)
        sys.exit(1)
    print('用户腿分发全程打通：分发的信封，用户确实能用自己的 d_A 解开。\n')


if __name__ == '__main__':
    main()
