"""
阶段 6（文档 §7.5）：密钥池项状态改为规范值。

unused → READY, used/distributed → CONSUMED, expired → EXPIRED。

为什么用 RunPython 而不是纯 schema 改动：
`status` 列本身没变（都是 varchar），变的是**取值语义**。
不迁移的话，库里既有行仍是旧值 —— 虽然读取侧已用
POOL_STATUS_READY_VALUES 兼容，但那只是兜底；把存量数据归一，
才能让「按状态统计」这类查询得到正确结果。

可逆：反向映射回旧值。虽然实际不会回退，但有 reverse 代码的迁移
比"不可逆"的更容易在出问题时处置。
"""
from django.db import migrations


FORWARD = {
    'unused': 'READY',
    'used': 'CONSUMED',
    'distributed': 'CONSUMED',
    'expired': 'EXPIRED',
}

BACKWARD = {
    'READY': 'unused',
    'CONSUMED': 'used',
    'EXPIRED': 'expired',
    # RESERVED / REVOKED 在旧模型里没有对应值，回退时置为 unused
    # （旧代码不认识它们，留在库里会变成"查不到的孤儿"）。
    'RESERVED': 'unused',
    'REVOKED': 'unused',
}


def _remap(apps, mapping):
    PreDistributedKey = apps.get_model('pqkds', 'PreDistributedKey')
    total = 0
    for old, new in mapping.items():
        n = PreDistributedKey.objects.filter(status=old).update(status=new)
        total += n
        if n:
            print(f"  {old} -> {new}: {n} 条")
    print(f"共更新 {total} 条")
    return total


def forwards(apps, schema_editor):
    print("阶段6：归一化密钥池项状态")
    _remap(apps, FORWARD)


def backwards(apps, schema_editor):
    print("阶段6：回退密钥池项状态")
    _remap(apps, BACKWARD)


class Migration(migrations.Migration):

    dependencies = [
        ("pqkds", "0009_distribution_domain"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]