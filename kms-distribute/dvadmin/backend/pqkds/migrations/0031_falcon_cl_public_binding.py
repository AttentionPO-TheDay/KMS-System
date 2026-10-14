from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0030_distribution_batch_item')]
    operations = [
        migrations.AddField(
            model_name='keygenerationissuance', name='partial_public_hash',
            field=models.CharField(max_length=64, blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='nodelongtermkey', name='algorithm',
            field=models.CharField(max_length=20, choices=[(a, a) for a in ('SM2', 'SSCL', 'KYBER', 'FALCON', 'FALCON_CL_V1')], verbose_name='算法', help_text='SM2 / SSCL / KYBER 可保护 SM4；FALCON 只签名'),
        ),
    ]
