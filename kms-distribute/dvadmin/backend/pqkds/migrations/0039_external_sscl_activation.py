from django.db import migrations, models
import django.db.models.deletion
from dvadmin.utils.models import table_prefix


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0038_nodekeydidrecord')]
    operations = [
        migrations.AddField(
            model_name='node', name='initialization_profile',
            field=models.CharField(max_length=24, default='FULL', choices=[('FULL', '完整节点'), ('EXTERNAL_SSCL', '外部托管SSCL节点')]),
        ),
        migrations.CreateModel(
            name='ExternalNodeActivation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identity_hash', models.CharField(max_length=64, unique=True)),
                ('client_id', models.CharField(max_length=64)),
                ('node_name', models.CharField(max_length=100)),
                ('encrypted_material', models.TextField()),
                ('lease_token', models.CharField(max_length=36, blank=True)),
                ('lease_expires_at', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='external_activation', to='pqkds.node')),
                ('key', models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='external_activation', to='pqkds.nodelongtermkey')),
            ],
            options={'db_table': table_prefix + 'pqkds_external_node_activations'},
        ),
    ]
