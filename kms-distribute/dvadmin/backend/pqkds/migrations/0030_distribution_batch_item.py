from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0029_node_key_inspection_disposition')]

    operations = [
        migrations.CreateModel(
            name='DistributionBatchItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_index', models.PositiveIntegerField()),
                ('payload_index', models.PositiveIntegerField()),
                ('recipient_type', models.CharField(max_length=10, choices=[('user', '用户'), ('node', '节点')])),
                ('recipient_user_id', models.BigIntegerField(null=True, blank=True)),
                ('recipient_node_code', models.CharField(max_length=64, blank=True, default='')),
                ('recipient_node_name', models.CharField(max_length=100, blank=True, default='')),
                ('recipient_key_id', models.CharField(max_length=64, null=True, blank=True)),
                ('recipient_key_version', models.PositiveIntegerField(null=True, blank=True)),
                ('wrapping_algorithm', models.CharField(max_length=20)),
                ('payload_algorithm', models.CharField(max_length=20, default='sm4')),
                ('delivery_status', models.CharField(max_length=20, choices=[
                    ('success', '信封已登记'), ('failed', '封装失败'),
                ])),
                ('signature_state', models.CharField(max_length=20, default='unverifiable', choices=[
                    ('valid', '签名有效'), ('invalid', '签名无效'),
                    ('missing', '无签名'), ('unverifiable', '无法验证'),
                ])),
                ('signature_message', models.CharField(max_length=255, blank=True, default='')),
                ('key_hash', models.CharField(max_length=64, blank=True, default='')),
                ('ciphertext_digest', models.CharField(max_length=64, blank=True, default='')),
                ('failure_reason', models.TextField(blank=True, default='')),
                ('expires_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='items', to='pqkds.distributionbatch')),
                ('recipient_node', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,
                                                     null=True, blank=True, related_name='distribution_items',
                                                     to='pqkds.node')),
                ('user_envelope', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,
                                                    null=True, blank=True, related_name='distribution_items',
                                                    to='pqkds.userkeyenvelope')),
                ('node_envelope', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,
                                                    null=True, blank=True, related_name='distribution_items',
                                                    to='pqkds.predistributedkey')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,
                                              null=True, blank=True, related_name='distribution_items',
                                              to='pqkds.sessionkey')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_distribution_batch_items',
                'ordering': ['item_index', 'id'],
                'constraints': [models.UniqueConstraint(fields=['batch', 'item_index'], name='pqkds_dist_item_uniq')],
                'indexes': [
                    models.Index(fields=['batch', 'delivery_status'], name='pqkds_dist_item_status'),
                    models.Index(fields=['recipient_node', 'recipient_key_id', 'recipient_key_version'],
                                 name='pqkds_dist_item_key'),
                    models.Index(fields=['recipient_user_id', 'created_at'], name='pqkds_dist_item_user'),
                    models.Index(fields=['expires_at'], name='pqkds_dist_item_expiry'),
                ],
            },
        ),
    ]
