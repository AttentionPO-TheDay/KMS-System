# -*- coding: utf-8 -*-
"""KMS-014：会话的证据轨迹列（监管页五态的数据源）。

计划 §7 阶段 6「监管页区分『已登记』『已验签』『已解封』『已建立』『已上链』」
----------------------------------------------------------------------------
前四态能从 `SessionKey.status` 推，**但只在会话还活着的时候** —— 关闭之后
status 只剩一个 `closed`，"它曾经走到过哪一步"就再也答不出来。而监管要看的
恰恰是完整轨迹（一条 established 后被关闭的会话，与一条没建立就被放弃的会话，
在审计上是两件完全不同的事）。

所以新增 `lifecycle_evidence`（JSON 文本）：每一步证据各记
`{"at": 时间, "tx": 链上哈希}`；`verified` / `established` / `closed` 三步
同时是链上事件（KMS-014 接通），`recovered`（本机解封）**没有**链上事件 ——
它是节点的单方声明、服务端无法独立复核（不变量：服务端没有 K），
如实记时间、tx 留空，不假装它上过链。

⚠️ 刻意**不**用 `status` 反推轨迹：反推在关闭/撤销后静默丢失轨迹，
且"五态"的语义本就是"证据各有其时间线，与当前状态无关"。
⚠️ 默认空字典 `{}`，**不**对历史行做任何回填：历史会话没有这些证据，
编一个时间比留空更糟（与迁移 0017/0019 同一条纪律）。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0020_pool_status_reserved_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionkey',
            name='lifecycle_evidence',
            field=models.TextField(
                default='{}',
                blank=True,
                verbose_name='会话证据轨迹',
                help_text='JSON：各步证据的时间与链上哈希（KMS-014，监管页五态的数据源）',
            ),
        ),
    ]
