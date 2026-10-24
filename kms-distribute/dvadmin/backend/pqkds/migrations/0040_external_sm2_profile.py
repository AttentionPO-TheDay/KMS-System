from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0039_external_sscl_activation')]
    operations = [
        migrations.AlterField(
            model_name='node', name='initialization_profile',
            field=models.CharField(max_length=24, default='FULL', choices=[
                ('FULL', '完整节点'), ('EXTERNAL_SSCL', '外部托管SSCL节点'),
                ('EXTERNAL_SM2', '外部托管SM2节点'),
            ]),
        ),
    ]
