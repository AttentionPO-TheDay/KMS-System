# -*- coding: utf-8 -*-
"""KMS-013：池项状态 choices 的两处如实化（纯结构，不写数据）。

计划 §7 阶段 5「预分配和密钥池重构」/ §8.4
------------------------------------------

一、`RESERVED` 的展示文案改为它的**实际身份**
--------------------------------------------
原文案「正在被某次会话占用」描述的是一个**从未发生过**的状态：全仓没有
任何生产写入点（KMS-013 逐处核对过 —— 只有 `security_monitor` 在读它），
消费路径是单事务的"选中（FOR UPDATE）→ 标记 CONSUMED"，中间没有需要
预留的时间段。留着旧文案的后果是**读代码的人以为存在预留语义**，据此
设计新流程（例如"先预留再消费"），而那个流程要配的过期与回收处置并不存在。

新文案直接写它是保留值，并指向 `api_contract.POOL_TRANSITIONS` ——
那张表里也没有任何指向它的边，强行写入会被状态机拒绝。

二、给 `'distributed'` 补上它的历史别名身份
------------------------------------------
`'distributed'` 是旧流程写入的"已下发"，语义上等价 CONSUMED，由
`api_contract.POOL_LEGACY_STATUS_ALIASES` 归一。但它的 choices 文案一直
单列着「已下发」，看列表的人无法知道**它在消费与清理里按 CONSUMED 处理**。
文案统一到"历史值，等价 CONSUMED"，与其他三个历史值同形。

⚠️ 两处都**只改 choices（Python 层校验）**，MySQL 层面状态列
   `varchar(20)` 不变，DDL 无差异；`AlterField` 应用时不会重写任何行，
   既有的 'unused' / 'distributed' 等历史取值原样保留 —— 不改写历史数据
   的口径与 0010/0011 一致。

⚠️ 与 0018 同样，本迁移**不写数据**；反向迁移只是把两处文案改回去。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0019_session_key_versions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='predistributedkey',
            name='status',
            field=models.CharField(
                choices=[
                    ('READY', '已预分配，可被会话取用'),
                    ('RESERVED', '保留值：从未产生（见 api_contract.POOL_TRANSITIONS）'),
                    ('CONSUMED', '已成功建立会话，不可再次使用'),
                    ('EXPIRED', '超过有效期'),
                    ('REVOKED', '依赖的长期密钥已回收或检测异常'),
                    ('unused', '未使用（历史值，等价 READY）'),
                    ('used', '已使用（历史值，等价 CONSUMED）'),
                    ('expired', '已过期（历史值，等价 EXPIRED）'),
                    ('distributed', '已下发（历史值，等价 CONSUMED）'),
                ],
                default='READY',
                max_length=20,
                verbose_name='状态',
                help_text='密钥当前状态；可用性与迁移规则见 api_contract.POOL_TRANSITIONS',
            ),
        ),
    ]
