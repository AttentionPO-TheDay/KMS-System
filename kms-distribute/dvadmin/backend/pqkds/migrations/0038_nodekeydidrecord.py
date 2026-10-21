import uuid
from django.db import migrations, models
import django.db.models.deletion
from dvadmin.utils.models import table_prefix


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0037_group_key_agreement')]
    operations = [migrations.CreateModel(
        name='NodeKeyDidRecord',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('request_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ('sys_pid', models.CharField(blank=True, max_length=182, null=True, unique=True)),
            ('chain_id', models.CharField(blank=True, max_length=128)),
            ('did', models.CharField(blank=True, max_length=512)),
            ('tx_id', models.CharField(blank=True, max_length=64)),
            ('status', models.CharField(default='PREPARING', max_length=32)),
            ('submit_started', models.BooleanField(default=False)),
            ('transaction_valid', models.BooleanField(null=True)),
            ('metadata_matches', models.BooleanField(null=True)),
            ('last_error', models.CharField(blank=True, max_length=80)),
            ('lease_token', models.CharField(blank=True, max_length=36)),
            ('lease_expires_at', models.DateTimeField(null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('key', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                       related_name='did_record', to='pqkds.nodelongtermkey')),
        ],
        options={'db_table': table_prefix + 'pqkds_node_key_did'},
    )]
