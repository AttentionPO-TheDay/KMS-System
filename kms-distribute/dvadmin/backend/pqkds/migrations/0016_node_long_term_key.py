# -*- coding: utf-8 -*-
"""KMS-004：新建 `NodeLongTermKey`（节点长期密钥版本表）并回填存量公钥。

计划 §6.1 / §15 第 1、2 步
--------------------------
新增整表，然后把 `Node` 上四个公钥列各回填成一条 `key_version=1` 的记录。

为什么必须回填而不是让它空着
--------------------------
新表是长期密钥的**唯一事实来源**，而 `Node.*_public_key` 从此是它的物化视图。
不回填的话，现网每一个已初始化的节点在新表里都是"没有长期密钥" ——
而分发路径 KMS-009 之后要按新表取接收方公钥，也就是说**所有存量节点
在下一次分发时会突然找不到公钥**。这不是"暂时不一致"，是功能中断。

回填出来的行状态一律 **ACTIVE**（不是 LEGACY）
---------------------------------------------
`legacy=True` 与 `status=LEGACY` 是两件事，别混：
  * `legacy=True`  —— "这行来自旧列的回填"，是**来源**标记；
  * `status=LEGACY` —— "来源不明、不可用于解封"，是**可用性**标记。
这四个列里装的就是现网正在用的公钥（大量既有代码直接 `node.kyber_public_key`
取值并拿它封装），标成 LEGACY 会让 `allows_unwrap` 立刻返回 False，
等于迁移一执行就把现网打死。所以：`legacy=True` + `status=ACTIVE`。

`falcon_public_key` 是唯一的例外，它拿不到 ACTIVE
-------------------------------------------------
同一个 `FALCON` 算法名对应 `Node` 上的**两列**，而它们装的东西互不兼容：
  * `falcon_sign_public_key` —— 标准 NIST Falcon-512，签名路径真正读的那一列；
  * `falcon_public_key`      —— CL-Falcon 格材料（D_id/S_id/H_id），
                                与标准 Falcon 不兼容，无法用于 crypto_sign。

两列都标 ACTIVE 会直接违反唯一约束，而且是把格材料谎报成"可用签名密钥"。
所以格材料那一条回填为 `status=LEGACY`、`key_id` 后缀 `-FALCON-CL`、
`legacy_source='falcon_public_key'`，只作审计留存。

选 LEGACY 而不是"看情况猜"是**保守方向**：万一某些节点的 `falcon_public_key`
里其实躺的是标准 Falcon 材料（历史修复脚本 `fix_all_falcon_keys.py` 动过这一列，
从迁移里无法判定），标 LEGACY 的后果是"这把签名密钥暂时不认，节点需要重新生成"
—— 会明确报 `SIGNATURE_REQUIRED`。反过来若把格材料标成 ACTIVE，后果是
服务端拿它去验签，**验不过却不知道是为什么**。宁可不认，不可误认。

（本迁移里没有 `legacy_unknown` 的行：四列的公钥列各自含义明确。
 真正需要 `legacy_unknown` 的是 `PreDistributedKey.wrapping_algorithm`
 与历史信封的 `source_key_id` —— 那些在 KMS-013/015 处理。）

⚠️ 本迁移**不碰** `NodeKeyVersion`：它表达"当前版本号"，
   而当前版本号可以从本表 status=ACTIVE 的行推出来。保留它只读。
"""

import hashlib

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


#: 回填来源：(Node 上的公钥列, 规范算法名, 安全级别, key_id 后缀)
#: 这四列回填为 ACTIVE —— 它们就是现网正在用的公钥。
ACTIVE_SOURCES = (
    ('kyber_public_key', 'KYBER', None, 'KYBER'),
    ('gm_public_key', 'SM2', 'sm2p256v1', 'SM2'),
    ('sscl_public_key', 'SSCL', 'sm2p256v1', 'SSCL'),
    ('falcon_sign_public_key', 'FALCON', None, 'FALCON'),
)

#: 单独处理：CL-Falcon 格材料，回填为 LEGACY（见文件头说明）。
LATTICE_SOURCE = ('falcon_public_key', 'FALCON', None, 'FALCON-CL')

_STATUS_ACTIVE = 'ACTIVE'
_STATUS_LEGACY = 'LEGACY'


def _legacy_key_id(node_id, suffix):
    """确定性的 key_id，使本迁移可重复执行而不产生重复行。

    `key_id` 列宽 64，而 `node_id` 自己就能占到 64 —— 直接拼接会溢出。
    溢出不会抛错（MySQL 非严格模式下截断），只会让两条不同节点的记录
    **撞成同一个 key_id**，进而撞唯一约束。所以超长时改用 node_id 的摘要。
    """
    raw = f'legacy-{node_id}-{suffix}'
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha256(str(node_id).encode('utf-8')).hexdigest()[:16]
    return f'legacy-{digest}-{suffix}'


def _hash(value):
    """与 `node_key_registry.hash_public_key` 同口径：对**存储形式的字符串**取摘要。"""
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()


def backfill_long_term_keys(apps, schema_editor):
    Node = apps.get_model('pqkds', 'Node')
    NodeLongTermKey = apps.get_model('pqkds', 'NodeLongTermKey')

    rows = []
    stats = {'ACTIVE': 0, 'LEGACY': 0, 'skipped': 0}

    for node in Node.objects.all().iterator():
        device_id = (getattr(node, 'key_device_id', '') or '')[:128]
        effective_at = node.initialized_at or node.create_datetime

        sources = [(col, alg, lvl, suf, _STATUS_ACTIVE) for col, alg, lvl, suf in ACTIVE_SOURCES]
        sources.append(LATTICE_SOURCE + (_STATUS_LEGACY,))

        for column, algorithm, fixed_level, suffix, status in sources:
            material = (getattr(node, column, '') or '').strip()
            if not material:
                continue

            key_id = _legacy_key_id(node.node_id, suffix)
            if NodeLongTermKey.objects.filter(
                node_id=node.pk, algorithm=algorithm, key_id=key_id, key_version=1,
            ).exists():
                # 重复执行（例如先回滚再迁移）时不重复插入。
                stats['skipped'] += 1
                continue

            if fixed_level is not None:
                security_level = fixed_level
            elif algorithm == 'KYBER':
                security_level = getattr(node, 'kyber_security_level', '') or ''
            else:
                security_level = getattr(node, 'falcon_security_level', '') or ''

            rows.append(NodeLongTermKey(
                node_id=node.pk,
                key_id=key_id,
                key_version=1,
                algorithm=algorithm,
                status=status,
                # ⚠️ 必须手写：`apps.get_model()` 拿到的是**历史模型**，
                #    只有字段、没有 NodeLongTermKey.save() 里那段派生逻辑。
                #    漏掉它的后果是唯一约束对回填行失效 —— 而且不报错。
                active_slot=algorithm if status == _STATUS_ACTIVE else None,
                public_key=material,
                public_key_hash=_hash(material),
                security_level=security_level[:20],
                device_id=device_id,
                effective_at=effective_at,
                legacy=True,
                legacy_source=column[:64],
            ))
            stats[status] += 1

    if rows:
        NodeLongTermKey.objects.bulk_create(rows, batch_size=200)

    print(
        f"[0016] 长期密钥回填完成: ACTIVE={stats['ACTIVE']} "
        f"LEGACY（CL-Falcon 格材料）={stats['LEGACY']} "
        f"已存在跳过={stats['skipped']}"
    )


def drop_backfilled(apps, schema_editor):
    """反向：只删回填来的行（`legacy=True`），不碰新登记路径写入的数据。"""
    NodeLongTermKey = apps.get_model('pqkds', 'NodeLongTermKey')
    deleted, _ = NodeLongTermKey.objects.filter(legacy=True).delete()
    print(f"[0016] 反向：已删除 {deleted} 条回填记录")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pqkds', '0015_node_device_credentials'),
    ]

    operations = [
        migrations.CreateModel(
            name='NodeLongTermKey',
            fields=[
                ('id', models.BigAutoField(help_text='Id', primary_key=True, serialize=False, verbose_name='Id')),
                ('description', models.CharField(blank=True, help_text='描述', max_length=255, null=True, verbose_name='描述')),
                ('modifier', models.CharField(blank=True, help_text='修改人', max_length=255, null=True, verbose_name='修改人')),
                ('dept_belong_id', models.CharField(blank=True, help_text='数据归属部门', max_length=255, null=True, verbose_name='数据归属部门')),
                ('update_datetime', models.DateTimeField(auto_now=True, help_text='修改时间', null=True, verbose_name='修改时间')),
                ('create_datetime', models.DateTimeField(auto_now_add=True, help_text='创建时间', null=True, verbose_name='创建时间')),
                ('key_id', models.CharField(db_index=True, max_length=64, verbose_name='密钥标识')),
                ('key_version', models.PositiveIntegerField(default=1, verbose_name='密钥版本')),
                ('algorithm', models.CharField(choices=[('SM2', 'SM2'), ('SSCL', 'SSCL'), ('KYBER', 'KYBER'), ('FALCON', 'FALCON')], help_text='SM2 / SSCL / KYBER 可保护 SM4；FALCON 只签名', max_length=20, verbose_name='算法')),
                ('status', models.CharField(choices=[('PENDING', '待启用'), ('ACTIVE', '生产中'), ('RETIRED', '已被取代'), ('REVOKED', '已回收'), ('EXPIRED', '已过期'), ('LEGACY', '历史记录（只读）')], db_index=True, default='PENDING', max_length=20, verbose_name='状态')),
                ('active_slot', models.CharField(blank=True, default=None, editable=False, help_text='status=ACTIVE 时为算法名，否则 NULL', max_length=20, null=True, verbose_name='生产槽位')),
                ('public_key', models.TextField(help_text='公开量，可自由落库与展示', verbose_name='公钥')),
                ('public_key_hash', models.CharField(max_length=64, verbose_name='公钥SHA256')),
                ('security_level', models.CharField(blank=True, default='', help_text='Kyber: 512/768/1024；Falcon: 512/1024；SM2/SSCL: sm2p256v1', max_length=20, verbose_name='安全级别')),
                ('device_id', models.CharField(blank=True, default='', help_text='生成并持有该版本私钥的设备标识；换设备后新版本记新设备', max_length=128, verbose_name='私钥所在设备')),
                ('effective_at', models.DateTimeField(blank=True, null=True, verbose_name='生效时间')),
                ('expires_at', models.DateTimeField(blank=True, null=True, verbose_name='过期时间')),
                ('revoked_at', models.DateTimeField(blank=True, null=True, verbose_name='回收时间')),
                ('revoked_reason', models.CharField(blank=True, default='', max_length=255, verbose_name='回收原因')),
                ('legacy', models.BooleanField(default=False, verbose_name='回填的历史记录')),
                ('legacy_source', models.CharField(blank=True, default='', help_text='从 Node 的哪一列回填而来；新登记路径写的行为空', max_length=64, verbose_name='回填来源列')),
                ('creator', models.ForeignKey(db_constraint=False, help_text='创建人', null=True, on_delete=django.db.models.deletion.SET_NULL, related_query_name='creator_query', to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='long_term_keys', to='pqkds.node', verbose_name='所属节点')),
            ],
            options={
                'verbose_name': '节点长期密钥',
                'verbose_name_plural': '节点长期密钥',
                'db_table': 'dvadmin_pqkds_node_long_term_keys',
                'ordering': ['node_id', 'algorithm', '-key_version'],
                'indexes': [
                    models.Index(fields=['node', 'algorithm', 'status'], name='pqkds_ltk_node_alg_status'),
                    models.Index(fields=['expires_at'], name='pqkds_ltk_expires_at'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['node', 'algorithm', 'key_id', 'key_version'],
                        name='pqkds_ltk_uniq_node_alg_id_ver',
                    ),
                    # 建在 active_slot 上，不是部分唯一索引 ——
                    # MySQL 不支持部分索引，Django 会静默跳过而不报错（见 models.py）。
                    models.UniqueConstraint(
                        fields=['node', 'active_slot'],
                        name='pqkds_ltk_uniq_active_per_node_alg',
                    ),
                ],
            },
        ),
        migrations.RunPython(backfill_long_term_keys, drop_backfilled),
    ]
