# -*- coding: utf-8 -*-
"""KMS-011：给 `SessionKey` 补四列 —— 会话关联的具体密钥版本。

计划 §7 阶段 4 第 1 条：「会话记录关联具体接收密钥版本和 Falcon 密钥版本」
------------------------------------------------------------------------------
补 `recipient_key_id` / `recipient_key_version`（这条会话的 SM4 靠接收方
哪一把长期密钥保护）与 `falcon_key_id` / `falcon_key_version`（发送方签名
用的那一版）。KMS-010 起分发请求里两条版本引用都是显式的，落进会话行
之后：接收方取信封时看得见"该用哪一版解封"，验收签回到**同一版**公钥，
不再靠 `{batch_id}-n{pk}` 反查或"当前生产版本"猜。

为什么必须补列，而不是继续从批次/信封反查
--------------------------------------------
  * 反查要拿 `batch_id` 拼会话 ID、再顺着批次找信封、解析 JSON 里的
    `recipient_key_version` —— 三个环节都是字符串约定，改一次命名规则
    历史会话就查不出自己的密钥版本，而查询**不会报错**，只会返回空；
  * 取信封页面上要显示"这封信靠哪一版解封"，这个信息必须随会话本身给出，
    否则页面只能显示一个自己拼的猜测值 —— 而"页面显示的版本"与
    "实际封装用的版本"对不上，正是本仓库反复踩过的那类静默错误。

为什么**不回填**历史行
----------------------
与迁移 0017 同一条纪律：表里没有信息能判定历史会话当初用的是哪一版
（旧用户腿流程读的是物化列，根本没有"指定版本"这个概念）。猜一个
版本号比留 NULL 更糟 —— 它会被下游当成真的去查，查到的是"碰巧同号的
另一把"。所以四列一律 NULL，页面如实显示"—"。

⚠️ 本迁移是**纯加列**（四个 `AddField`），不写数据；反向迁移只丢这四列，
   会话本身与状态一动不动。

写入点
------
`distribution_service.create_initiated_sessions`（节点间分发：两条都写；
旧用户腿流程：只写 falcon 两条，接收密钥版本留 NULL）。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0018_distribution_request_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionkey',
            name='recipient_key_id',
            field=models.CharField(
                blank=True, null=True, max_length=64,
                verbose_name='接收方长期密钥 keyId',
                help_text='这条会话的 SM4 是靠接收方哪一把长期密钥保护的（KMS-011）',
            ),
        ),
        migrations.AddField(
            model_name='sessionkey',
            name='recipient_key_version',
            field=models.IntegerField(
                blank=True, null=True,
                verbose_name='接收方长期密钥版本',
            ),
        ),
        migrations.AddField(
            model_name='sessionkey',
            name='falcon_key_id',
            field=models.CharField(
                blank=True, null=True, max_length=64,
                verbose_name='发送方 Falcon keyId',
                help_text='发送节点签名这封信封用的 Falcon 密钥（验收签要用同一版）',
            ),
        ),
        migrations.AddField(
            model_name='sessionkey',
            name='falcon_key_version',
            field=models.IntegerField(
                blank=True, null=True,
                verbose_name='发送方 Falcon 版本',
            ),
        ),
    ]