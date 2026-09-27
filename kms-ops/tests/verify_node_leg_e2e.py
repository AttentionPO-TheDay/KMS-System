# -*- coding: utf-8 -*-
"""节点腿验收：**两条腿必须解出同一把 K**（P3 步骤 6 / D10）。

这是 D10 方案 A 成立与否的唯一判据
----------------------------------
计划 §3.1：用户要与节点用**同一把 SM4** 通信，双方都必须持有 K。
用户那份走国密 SM2，节点那份走抗量子 Kyber —— **两条腿算法不同，但解出的 K 必须相同**。

因此"两条腿各自都能解开"**不算通过**：如果实现里各生成了一把 K，
两边都能解开自己的信封，验收却完全通不过真实需求 ——
用户发给节点的消息，节点根本解不开。所以这里必须**解开两条腿再比对是不是同一把**。

做法（在容器内跑，复用经国标向量验证过的 sm2_crypto 与 KyberCrypto）：
    1. 自己生成已知的本地份额 u → 登记 SM2 密钥 → 算出 d_A；
    2. 分发到两个节点；
    3. 用户腿：从 `user-symmetric-keys` 取信封 → 用 d_A 解开 → K_user；
    4. 节点腿：从 `pre_distributed_keys` 取节点信封 → 用节点 Kyber 私钥解开 → K_node；
    5. **断言 K_user == K_node**，且与库中 key_hash 一致。

用法：docker exec -w /backend dvadmin3-django python /tmp/verify_node_leg_e2e.py
"""

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
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
    django.setup()

    from pqkds.crypto_utils import KyberCrypto
    from pqkds.models import Node, PreDistributedKey
    from pqkds.wrappers import open_node_envelope

    print('\n=== 节点腿验收：两条腿必须解出同一把 K ===\n')

    login = requests.post(f'{GATEWAY}/lifecycle-api/login',
                          json={'username': 'yx', 'password': 'admin123'}, timeout=15).json()
    token = login.get('token')
    if not token:
        print('  登录失败')
        sys.exit(1)
    auth = {'Authorization': 'Bearer ' + token}

    # --- 1. 已知 u 的密钥 ---
    u = secrets.randbelow(SM2_N - 1) + 1
    u_hex = format(u, '064x')
    ua = SM2Crypto.public_key_of(u_hex)

    key_name = 'e2e-节点腿-%d' % int(time.time())
    requests.post(f'{GATEWAY}/generate-api/generate/keymanage',
                  headers={**auth, 'Content-Type': 'application/json'},
                  json={'encrytType': '无证书非对称加密', 'encrytName': 'SM2',
                        'keyName': key_name, 'keyUse': 'E2E 节点腿', 'keyDomain': 'A', 'uA': ua},
                  timeout=20)

    key_id = None
    for _ in range(30):
        rows = requests.get(f'{GATEWAY}/generate-api/generate/key/list?pageSize=200',
                            headers=auth, timeout=20).json().get('rows') or []
        hit = [r for r in rows if r.get('keyName') == key_name]
        if hit:
            key_id = hit[0]['keyId']
            break
        time.sleep(0.7)
    check('密钥已入库', key_id is not None, 'keyId=%s' % key_id)
    if key_id is None:
        sys.exit(1)

    detail = requests.get(f'{GATEWAY}/lifecycle-api/lifecycle/keymanage/{key_id}',
                          headers=auth, timeout=20).json().get('data') or {}
    material = detail.get('key_value') or detail.get('keyValue')
    if isinstance(material, str):
        material = json.loads(material)
    d_a_hex = format((int(material['partialKey'], 16) + u) % SM2_N, '064x')

    # --- 2. 分发 ---
    nodes = (requests.get(f'{GATEWAY}/pqkds-api/user-nodes/', headers=auth, timeout=20)
             .json().get('data') or {}).get('nodes') or []
    node_ids = [n['nodeId'] for n in nodes[:2]]
    dist = requests.post(f'{GATEWAY}/pqkds-api/key-pool/distribute-to-user/',
                         headers={**auth, 'Content-Type': 'application/json'},
                         json={'source_key_id': key_id, 'node_ids': node_ids, 'count': 2},
                         timeout=90).json().get('data') or {}
    batch_id = dist.get('batchId')
    check('分发成功', bool(batch_id), 'batch=%s status=%s' % (batch_id, dist.get('status')))
    check('★ 批次状态为 success（节点腿真的投递了，而不是如实记 partial）',
          dist.get('status') == 'success',
          'status=%s nodeResults=%s' % (dist.get('status'),
                                        [(n.get('nodeCode'), n.get('delivered')) for n in (dist.get('nodeResults') or [])]))

    # --- 3. 用户腿解开 ---
    keys = (requests.get(f'{GATEWAY}/pqkds-api/user-symmetric-keys/', headers=auth, timeout=20)
            .json().get('data') or {}).get('items') or []
    mine = [k for k in keys if k.get('sourceKeyId') == key_id]
    check('「对称密钥查看」里有本批信封', len(mine) >= 1, '条数=%d' % len(mine))
    if not mine:
        sys.exit(1)

    user_keys = {}
    for item in mine:
        one = requests.get(f'{GATEWAY}/pqkds-api/user-symmetric-keys/{item["id"]}/',
                           headers=auth, timeout=20).json().get('data') or {}
        env = one.get('encryptedKeyData')
        env = json.loads(env) if isinstance(env, str) else env
        k = SM2Crypto.decrypt(d_a_hex, env)
        check('用户腿解封成功且哈希与库中一致 (#%s)' % item['id'],
              hashlib.sha256(k).hexdigest() == item.get('keyHash'))
        user_keys[item.get('keyHash')] = k

    # --- 4. 节点腿解开 ---
    records = list(PreDistributedKey.objects.filter(pool_id=batch_id).select_related('node1'))
    check('库里存下了节点腿信封', len(records) > 0, '条数=%d' % len(records))

    matched = 0
    for rec in records:
        node = rec.node1
        if not node.kyber_private_key:
            check('节点 %s 有 Kyber 私钥' % node.node_id, False, '私钥为空')
            continue
        envelope = json.loads(rec.encrypted_key_data)
        k_node = open_node_envelope(envelope, node.kyber_private_key)
        check('节点腿解封成功 (%s)' % node.node_id,
              hashlib.sha256(k_node).hexdigest() == rec.key_hash)
        # ★ 决定性断言
        same = user_keys.get(rec.key_hash)
        if same is not None:
            check('★ 节点 %s 解出的 K 与用户腿**是同一把**' % node.node_id,
                  k_node == same,
                  '一致（%d 字节）' % len(k_node) if k_node == same else '不一致！两条腿各持一把 K')
            matched += 1

    check('至少比对过一组双人腿密钥', matched >= 1, '比对 %d 组' % matched)

    # --- 5. 反向：换一把 Kyber 私钥应解不开 ---
    if records:
        from pqkds.crypto_utils import KyberCrypto as _K
        other = _K(512)
        pk2, sk2 = other.generate_keypair()
        import base64 as _b64
        try:
            bad = open_node_envelope(json.loads(records[0].encrypted_key_data),
                                     _b64.b64encode(sk2).decode())
            check('陌生节点私钥解不开', False, '竟然解出了 %d 字节' % len(bad))
        except Exception:
            check('陌生节点私钥解不开（信封确实只对该节点开放）', True)

    print('\n== 结果：%d 通过 / %d 失败 ==' % (_pass, _fail))
    if _fail:
        print('失败项：')
        for item in _failures:
            print('  - %s' % item)
        sys.exit(1)
    print('节点腿与用户腿解出同一把 K —— D10「两条腿算法不同、K 相同」成立。\n')


if __name__ == '__main__':
    main()
