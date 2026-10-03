# -*- coding: utf-8 -*-
"""KMS-008：新分发请求模型落库所需的两处结构变更。

计划 §7 阶段 3 / §13 KMS-008「重构分发请求模型」
------------------------------------------------
新契约是**节点到节点**的分发：发送节点 + 接收节点 + 保护算法 +
**接收方 key_id/version（显式）** + 有效期。它不再有"我的解封密钥"
（`source_key_id`），也不再"一律 kyber_kem"。两处模型随之调整。

一、`DistributionBatch.source_key_id` 改为可空
---------------------------------------------
该列装的是**旧用户腿**流程里"用户选来给自己解封的那把非对称密钥"
（`kms.keymanage.key_id`，另一库的逻辑引用）。新流程没有这个概念 ——
发送方是节点，接收方也是节点，中间不经过任何用户密钥。

为什么是 NULL 而不是 0：
  * 0 会被下游当成一把**真的** key_id 去查。`LifecycleService` 的泄漏分析
    就是按 `WHERE source_key_id = ?` 跨库查的 —— 填 0 之后，"查 0 号密钥"
    会把所有新批次一次性带出来，看起来像"这把密钥影响了全部会话"；
  * 而 NULL 不会被 `= ?` 命中，语义上就是"这条记录没有来源密钥"。

⚠️ 如实记录的过渡缺口：泄漏分析（`LifecycleService.getKeyLeakAnalysis`）
   按 `source_key_id` 反查分发足迹，因此**新批次不会出现在该分析里**。
   计划 §7 阶段 6 已把「泄漏分析按具体密钥版本追踪受影响信封、池项和会话」
   列为 **KMS-014** 的范围 —— 新流程的关联键是"接收方那一版长期密钥"
   （`PreDistributedKey.long_term_key_id/version`，KMS-007 已补），
   那条查询要一起改，本次不越界动 Java。

二、`SessionKey.session_type` 的 choices 补两个国密取值
------------------------------------------------------
本字段在 `node_session_views` 里以 `protectionAlgorithm` 的名义下发 ——
也就是"这条会话用哪种算法保护"。而它的 choices 里只有
`aes_falcon` / `kyber_kem`：旧用户腿流程无论节点腿用 kyber 还是国密，
**一律写 `kyber_kem`**，那是一条一直被如实保留的失真。

KMS-008 的新流程按**实际使用的保护算法**记（`gm_sm2` / `gm_sscl` / `kyber_kem`），
所以 choices 要能表达它们。取值与 `wrappers.NODE_WRAPPING_CHOICES` 同形，
避免出现第二套算法拼写。

⚠️ 本操作**只改 choices（Python 层校验）**，MySQL 层面 `varchar(20)` 不变，
   DDL 无差异；`AlterField` 由 Django 生成，应用它不会重写任何既有行。
   旧行里的 `kyber_kem` 保持原值 —— 不改写历史数据的口径。

⚠️ 与 0017 同样，本迁移是**纯结构变更**，不写数据：
   反向迁移只把两处改回去（`source_key_id` 恢复 NOT NULL 只在无 NULL 行时
   才可能成功 —— 这正是"回滚不能凭空造出一个来源密钥"的如实表达）。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0017_pool_long_term_key_ref'),
    ]

    operations = [
        migrations.AlterField(
            model_name='distributionbatch',
            name='source_key_id',
            field=models.BigIntegerField(
                blank=True, null=True,
                verbose_name='来源密钥ID',
                help_text='旧用户腿流程里用户所选的非对称密钥；节点间分发为 NULL',
            ),
        ),
        migrations.AlterField(
            model_name='sessionkey',
            name='session_type',
            field=models.CharField(
                choices=[
                    ('aes_falcon', 'AES+Falcon会话'),
                    ('kyber_kem', 'Kyber密钥协商'),
                    ('gm_sm2', '国密 SM2 保护'),
                    ('gm_sscl', '国密 SSCL 保护'),
                ],
                default='aes_falcon',
                max_length=20,
                verbose_name='会话类型',
                help_text='会话建立的协议类型 = 本次分发用的保护算法拼写',
            ),
        ),
    ]
