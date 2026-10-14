import uuid

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0032_acceptance_preallocation_evidence')]

    operations = [
        migrations.CreateModel(
            name='DidSdkHandoff',
            fields=[
                ('record_id', models.UUIDField(default=uuid.uuid4, editable=False,
                                               primary_key=True, serialize=False)),
                ('node_id_snapshot', models.CharField(max_length=64)),
                ('algorithm', models.CharField(max_length=20)),
                ('key_id', models.CharField(max_length=64)),
                ('key_version', models.PositiveIntegerField()),
                ('key_status', models.CharField(max_length=20)),
                ('sequence', models.PositiveBigIntegerField()),
                ('event_id', models.CharField(max_length=64, unique=True)),
                ('interface_path', models.CharField(
                    default='/internal/fabric-did/bindings/handoff', max_length=128)),
                ('request_payload', models.TextField()),
                ('request_digest', models.CharField(max_length=64)),
                ('prepare_status', models.CharField(
                    choices=[('RECORDED', 'RECORDED'), ('PREPARED', 'PREPARED'),
                             ('NOT_CONFIGURED', 'NOT_CONFIGURED'),
                             ('BRIDGE_UNAVAILABLE', 'BRIDGE_UNAVAILABLE'),
                             ('FAILED', 'FAILED')],
                    db_index=True, default='RECORDED', max_length=24)),
                ('prepared_payload', models.TextField(blank=True, default='')),
                ('did', models.CharField(blank=True, default='', max_length=512)),
                ('tx_id', models.CharField(blank=True, default='', max_length=256)),
                ('nonce', models.TextField(blank=True, default='')),
                ('last_error', models.CharField(blank=True, default='', max_length=64)),
                ('requested_by', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('long_term_key', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='did_sdk_handoffs', to='pqkds.nodelongtermkey')),
                ('node', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='did_sdk_handoffs', to='pqkds.node')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_did_sdk_handoffs',
                'ordering': ['-created_at', '-sequence'],
                'indexes': [models.Index(fields=['node', '-created_at'],
                                         name='pqkds_did_handoff_node_time')],
                'constraints': [models.UniqueConstraint(
                    fields=('node', 'sequence'), name='pqkds_did_handoff_node_sequence')],
            },
        ),
    ]
