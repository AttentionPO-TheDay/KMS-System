from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0033_did_sdk_handoff')]
    operations = [migrations.CreateModel(
        name='NodeKeyAutoUpdate',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('algorithm', models.CharField(max_length=20)),
            ('key_id', models.CharField(max_length=64)),
            ('enabled', models.BooleanField(default=False)),
            ('interval_minutes', models.PositiveIntegerField(default=1440)),
            ('next_run_at', models.DateTimeField(blank=True, null=True)),
            ('last_run_at', models.DateTimeField(blank=True, null=True)),
            ('last_result', models.CharField(blank=True, default='', max_length=20)),
            ('last_message', models.CharField(blank=True, default='', max_length=500)),
            ('lease_token', models.CharField(blank=True, default='', max_length=36)),
            ('lease_until', models.DateTimeField(blank=True, null=True)),
            ('from_version', models.PositiveIntegerField(default=0)),
            ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pqkds.node')),
        ],
        options={
            'db_table': 'dvadmin_pqkds_node_key_auto_update',
            'constraints': [models.UniqueConstraint(fields=('node', 'algorithm'), name='pqkds_auto_update_node_alg')],
        },
    )]
