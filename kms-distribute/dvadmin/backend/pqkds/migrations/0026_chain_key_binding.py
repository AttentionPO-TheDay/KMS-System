# -*- coding: utf-8 -*-
"""纯新增表，不迁移现有节点，不触碰旧合约、交易或业务密钥。"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0025_key_distribution_log_pool_actions')]

    operations = [
        migrations.CreateModel(
            name='ChainKeyBinding',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('provider', models.CharField(default='FABRIC_DID', max_length=20)),
                ('chain_id', models.CharField(blank=True, default='', max_length=128)),
                ('namespace', models.CharField(default='kms-key-binding-v1', max_length=80)),
                ('node_id_snapshot', models.CharField(max_length=64)),
                ('algorithm', models.CharField(max_length=20)),
                ('key_id', models.CharField(max_length=64)),
                ('key_version', models.PositiveIntegerField()),
                ('key_ref', models.CharField(max_length=256)),
                ('event_type', models.CharField(max_length=20)),
                ('key_status', models.CharField(max_length=20)),
                ('sequence', models.PositiveBigIntegerField()),
                ('event_id', models.CharField(max_length=64, unique=True)),
                ('metadata', models.TextField()),
                ('metadata_digest', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[(s, s) for s in ('PENDING', 'PREPARED', 'SUBMITTED', 'PENDING_VERIFICATION', 'CONFIRMED', 'FAILED', 'NOT_CONFIGURED', 'UNSUPPORTED')], db_index=True, default='PENDING', max_length=24)),
                ('did', models.CharField(blank=True, default='', max_length=512)),
                ('tx_id', models.CharField(blank=True, default='', max_length=256)),
                ('nonce', models.TextField(blank=True, default='')),
                ('submit_started', models.BooleanField(default=False)),
                ('transaction_valid', models.BooleanField(default=False)),
                ('metadata_matches', models.BooleanField(default=False)),
                ('lease_token', models.CharField(blank=True, default='', max_length=32)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.CharField(blank=True, default='', max_length=255)),
                ('recorded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('node', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chain_key_bindings', to='pqkds.node')),
                ('long_term_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chain_bindings', to='pqkds.nodelongtermkey')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_chain_key_bindings',
                'ordering': ['node_id', 'sequence'],
                'indexes': [models.Index(fields=['node', 'status', 'sequence'], name='pqkds_binding_node_state')],
                'constraints': [
                    models.UniqueConstraint(fields=('provider', 'chain_id', 'namespace', 'key_ref', 'event_type', 'key_status'), name='pqkds_binding_uniq_event'),
                    models.UniqueConstraint(fields=('node', 'sequence'), name='pqkds_binding_node_sequence'),
                ],
            },
        ),
    ]
