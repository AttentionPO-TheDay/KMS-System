# 给节点加国密（SM2）密钥字段。
#
# 背景（2026-09-26）：节点腿上原本只有抗量子（Kyber/Falcon），于是"这次分发不用抗量子"
# 在界面上无路可走 —— 节点表里根本没有国密密钥可用。加这三个字段后：
#   * 节点可持有 SM2 密钥对（服务端生成、私钥随节点保存）；
#   * 分发时用户可三选一：kyber_kem / falcon_lattice / gm_sm2；
#   * 选 gm_sm2 时节点信封用 gm_public_key 封装，节点用 gm_private_key 解封。
#
# 字段与既有 kyber_*/falcon_* 保持同样的形状（TextField(blank=True) + 生成时间），
# 便于列表序列化与「节点管理」页统一展示。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0006_node2_nullable_for_user_distribution'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='gm_public_key',
            field=models.TextField(blank=True, help_text='SM2 公钥（130 位十六进制，04 开头）', verbose_name='国密公钥'),
        ),
        migrations.AddField(
            model_name='node',
            name='gm_private_key',
            field=models.TextField(blank=True, help_text='SM2 私钥（64 位十六进制标量），仅节点本地存储', verbose_name='国密私钥'),
        ),
        migrations.AddField(
            model_name='node',
            name='gm_keygen_time',
            field=models.DateTimeField(blank=True, help_text='SM2 节点密钥对生成的时间', null=True, verbose_name='国密密钥生成时间'),
        ),
        migrations.AddField(
            model_name='node',
            name='sscl_public_key',
            field=models.TextField(blank=True, help_text='SSCL 加密目标点（130 位十六进制，04 开头）', verbose_name='SSCL 公钥'),
        ),
        migrations.AddField(
            model_name='node',
            name='sscl_private_key',
            field=models.TextField(blank=True, help_text='SSCL 私钥标量（64 位十六进制），仅节点本地存储', verbose_name='SSCL 私钥'),
        ),
    ]