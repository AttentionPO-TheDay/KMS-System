# 节点设备凭据认证（文档 §3 激活 / §5 登录）。
#
# 本迁移给 Node 增加两样东西：
#   1. 设备认证**公钥** —— 节点侧不可导出的 ECDSA P-256 私钥对应的公开量，
#      用于登录挑战-应答验签。这是 key_device_id 的**升级**：
#      后者是自报的随机串、服务端无法验证（模型注释里已说明），
#      前者能真正证明"签名的是那台设备"。
#   2. 一次性激活凭证的**哈希**与时效 —— 文档 §3 的激活机制。
#      只存哈希，明文只在签发响应里出现一次。
#
# 全部字段都有默认值（'' 或 NULL），对既有行是安全的空操作 ——
# 已存在的节点保持"未激活"状态，管理员重新签发凭证即可。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0014_node_key_device_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='device_auth_public_key',
            field=models.TextField(
                blank=True, default='',
                help_text='ECDSA P-256 公钥（JWK JSON）；登录挑战-应答验签用。私钥只在节点本机',
                verbose_name='设备认证公钥'),
        ),
        migrations.AddField(
            model_name='node',
            name='device_auth_algorithm',
            field=models.CharField(
                blank=True, default='ECDSA-P256', max_length=32,
                help_text='便于日后换算法时不必猜旧值是什么',
                verbose_name='设备认证算法'),
        ),
        migrations.AddField(
            model_name='node',
            name='activation_code_hash',
            field=models.CharField(
                blank=True, default='', max_length=128,
                help_text='一次性激活凭证的 SHA-256 十六进制；明文只在签发响应里出现一次',
                verbose_name='激活凭证哈希'),
        ),
        migrations.AddField(
            model_name='node',
            name='activation_code_issued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='凭证签发时间'),
        ),
        migrations.AddField(
            model_name='node',
            name='activation_code_expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='凭证过期时间'),
        ),
        migrations.AddField(
            model_name='node',
            name='activated_at',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text='节点首次用激活凭证换取设备凭据的时间',
                verbose_name='设备激活时间'),
        ),
    ]
