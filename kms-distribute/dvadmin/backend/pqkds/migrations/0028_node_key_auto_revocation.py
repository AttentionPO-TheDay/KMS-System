from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0027_split_keygen_public_provenance')]

    operations = [
        migrations.AlterField(
            model_name='sessionkeyinvalidation', name='reason',
            field=models.CharField(max_length=30, verbose_name='失效原因',
                                   help_text='会话失效的原因', choices=[
                ('node1_key_updated', '节点1密钥已更新'),
                ('node2_key_updated', '节点2密钥已更新'),
                ('both_keys_updated', '两个节点密钥都已更新'),
                ('manual_revocation', '手动撤销'),
                ('automatic_revocation', '异常密钥自动回收'),
            ]),
        ),
        migrations.CreateModel(
            name='NodeKeyAutoRevocationBatch',
            fields=[
                ('batch_id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('started_at', models.DateTimeField()),
                ('completed_at', models.DateTimeField()),
                ('key_count', models.PositiveIntegerField()),
                ('pool_count', models.PositiveIntegerField()),
                ('session_count', models.PositiveIntegerField()),
                ('elapsed_ms', models.PositiveIntegerField()),
            ],
            options={'db_table': 'dvadmin_pqkds_node_key_revoke_batches'},
        ),
        migrations.CreateModel(
            name='NodeKeyInspection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule', models.CharField(max_length=40)),
                ('severity', models.CharField(max_length=10)),
                ('action', models.CharField(max_length=20)),
                ('detected_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('action_at', models.DateTimeField(blank=True, null=True)),
                ('batch_id', models.CharField(blank=True, default='', max_length=36)),
                ('key', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='inspection', to='pqkds.nodelongtermkey')),
            ],
            options={'db_table': 'dvadmin_pqkds_node_key_inspections'},
        ),
        migrations.AddIndex(
            model_name='nodekeyinspection',
            index=models.Index(fields=['action', '-detected_at'], name='pqkds_inspection_action'),
        ),
        migrations.AddIndex(
            model_name='sessionkey',
            index=models.Index(fields=['node2', 'recipient_key_id', 'recipient_key_version', 'status'],
                               name='pqkds_sess_recipient'),
        ),
        migrations.AddIndex(
            model_name='sessionkey',
            index=models.Index(fields=['node1', 'falcon_key_id', 'falcon_key_version', 'status'],
                               name='pqkds_sess_falcon'),
        ),
        migrations.AddIndex(
            model_name='predistributedkey',
            index=models.Index(fields=['long_term_key_id', 'long_term_key_version', 'status'],
                               name='pqkds_pool_key_status'),
        ),
    ]
