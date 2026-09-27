# -*- coding: utf-8 -*-
"""造一份"浏览器端解封"验收样本：已知 d_A 的密钥 + 已分发到该密钥的信封。

为什么不用固定样本
------------------
`symmetric_keys` 里的信封是用**当时那把 d_A 的公钥**封的，而 `d_A` 只在生成它的
那个页面里存在过。所以要验"浏览器能不能解开"，必须自己造一把**私钥已知**的密钥，
用它的 `P_A` 走一次真实分发，然后把 `d_A` 作为密钥文件交给浏览器。

输出 JSON：{keyId, userId, privateShare, publicKey, batchId}
"""

import json
import secrets
import sys
import time

import requests

sys.path.insert(0, '/backend')

from pqkds.sm2_crypto import SM2Crypto  # noqa: E402

GATEWAY = 'http://nginx'
SM2_N = int('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/browser_sample.json'

    token = requests.post(f'{GATEWAY}/lifecycle-api/login',
                          json={'username': 'yx', 'password': 'admin123'}, timeout=15).json()['token']
    auth = {'Authorization': 'Bearer ' + token}

    u = secrets.randbelow(SM2_N - 1) + 1
    ua = SM2Crypto.public_key_of(format(u, '064x'))
    name = 'browser-decrypt-%d' % int(time.time())

    requests.post(f'{GATEWAY}/generate-api/generate/keymanage',
                  headers={**auth, 'Content-Type': 'application/json'},
                  json={'encrytType': '无证书非对称加密', 'encrytName': 'SM2', 'keyName': name,
                        'keyUse': '浏览器解封验收', 'keyDomain': 'A', 'uA': ua}, timeout=20)

    key_id = None
    for _ in range(30):
        rows = requests.get(f'{GATEWAY}/generate-api/generate/key/list?pageSize=200',
                            headers=auth, timeout=20).json().get('rows') or []
        hit = [r for r in rows if r.get('keyName') == name]
        if hit:
            key_id = hit[0]['keyId']
            break
        time.sleep(0.7)
    if key_id is None:
        raise SystemExit('密钥未入库，无法造样本')

    detail = requests.get(f'{GATEWAY}/lifecycle-api/lifecycle/keymanage/{key_id}',
                          headers=auth, timeout=20).json()['data']
    material = detail.get('key_value') or detail.get('keyValue')
    if isinstance(material, str):
        material = json.loads(material)

    # d_A = t_A + u mod n —— 这正是前端在做的事
    d_a = format((int(material['partialKey'], 16) + u) % SM2_N, '064x')
    p_a = SM2Crypto.public_key_of(d_a)

    nodes = (requests.get(f'{GATEWAY}/pqkds-api/user-nodes/', headers=auth, timeout=20)
             .json().get('data') or {}).get('nodes') or []
    if not nodes:
        raise SystemExit('当前用户没有已授权节点，无法分发')

    dist = requests.post(f'{GATEWAY}/pqkds-api/key-pool/distribute-to-user/',
                         headers={**auth, 'Content-Type': 'application/json'},
                         json={'source_key_id': key_id, 'node_ids': [nodes[0]['nodeId']], 'count': 1},
                         timeout=90).json()['data']

    sample = {
        'keyId': key_id,
        'userId': 2,
        'privateShare': d_a,
        'publicKey': p_a,
        'batchId': dist.get('batchId'),
    }
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(sample, fh, ensure_ascii=False)
    print(json.dumps(sample, ensure_ascii=False))


if __name__ == '__main__':
    main()
