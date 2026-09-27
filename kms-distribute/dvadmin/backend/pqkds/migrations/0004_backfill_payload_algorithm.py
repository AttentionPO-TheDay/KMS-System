# -*- coding: utf-8 -*-
"""回填 `payload_algorithm`：按信封内容判定历史行的载荷算法。

背景（决策 D3 / 计划 P2 第 5 步）
--------------------------------
`dvadmin_pqkds_pre_distributed_keys.payload_algorithm` 是本次新增的列，用来区分
被封装的那把对称密钥用的是哪种算法：

  * `sm4`     —— 2026-09 之后写入（D3 之后的新数据）
  * `aes_256` —— 更早写入的历史数据

**为什么必须回填而不是靠默认值**：该列的 `default='sm4'` 只对**新插入**的行生效；
既有行在 `AddField` 时会被一次性写成默认值 `sm4`，而它们实际上是 AES-256。
如果不纠正，读取端就会拿 16 字节的 KEK 和 SM4 去解一条 AES 密文，
现象是"历史密钥池全部解不开"，而且是静默的算法错配。

判定依据用**信封内容**而非迁移时间：新写入的信封里带 `payload_algorithm` 字段
（见 `key_pool_service.py`），历史信封没有。这比"按时间切一刀"可靠，
也能正确处理"迁移执行前刚好写了一行新数据"的边界情况。
"""

import json

from django.db import migrations


def _algorithm_of(envelope_text):
    """按信封内容判定算法；解析不出来就保守地当历史 AES 处理。"""
    if not envelope_text:
        return 'aes_256'
    try:
        envelope = json.loads(envelope_text)
    except (ValueError, TypeError):
        return 'aes_256'
    if not isinstance(envelope, dict):
        return 'aes_256'
    marked = envelope.get('payload_algorithm') or envelope.get('payloadAlgorithm')
    if marked is None:
        # 没有标记 = 2026-09 之前写的 = AES-256
        return 'aes_256'
    return 'sm4' if str(marked).strip().lower().replace('-', '_') in ('sm4', 'gm_sm4', 'sm4_gcm') else 'aes_256'


def backfill_payload_algorithm(apps, schema_editor):
    PreDistributedKey = apps.get_model('pqkds', 'PreDistributedKey')

    counts = {'sm4': 0, 'aes_256': 0}
    # 只遍历需要纠正的行（默认值把它们错误地标成了 sm4）
    for row in PreDistributedKey.objects.all().only('id', 'encrypted_key_data', 'payload_algorithm').iterator():
        expected = _algorithm_of(row.encrypted_key_data)
        if row.payload_algorithm != expected:
            row.payload_algorithm = expected
            row.save(update_fields=['payload_algorithm'])
        counts[expected] += 1

    print(f"[003/004] payload_algorithm 回填完成: sm4={counts['sm4']} aes_256={counts['aes_256']}")


def noop_reverse(apps, schema_editor):
    """回滚不做处理：把列删掉即可（该迁移的 reverse 由 0003 负责）。"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0003_add_payload_algorithm'),
    ]

    operations = [
        migrations.RunPython(backfill_payload_algorithm, noop_reverse),
    ]