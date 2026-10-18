from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from dvadmin.utils.models import table_prefix


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0036_domain')]
    operations = [
        migrations.CreateModel(name='GroupKeyAgreement', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('agreement_id', models.CharField(max_length=64, unique=True)),
            ('initiator_node_code', models.CharField(max_length=64)),
            ('roster', models.JSONField(default=list)),
            ('channels', models.JSONField(default=list)),
            ('scope_hash', models.CharField(max_length=64)),
            ('transcript_hash', models.CharField(blank=True, max_length=64)),
            ('status', models.CharField(default='committing', max_length=20)),
            ('failure_reason', models.CharField(blank=True, max_length=200)),
            ('events', models.JSONField(default=list)),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ('expires_at', models.DateTimeField()),
            ('initiator', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                           related_name='initiated_agreements', to='pqkds.node')),
        ], options={'db_table': f'{table_prefix}pqkds_group_agreements', 'ordering': ['-created_at', '-id']}),
        migrations.CreateModel(name='GroupAgreementMember', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('commitment', models.CharField(blank=True, max_length=64)),
            ('participant_node_code', models.CharField(max_length=64)),
            ('packets', models.JSONField(default=list)),
            ('proof', models.CharField(blank=True, max_length=64)),
            ('committed_at', models.DateTimeField(null=True)),
            ('exchanged_at', models.DateTimeField(null=True)),
            ('confirmed_at', models.DateTimeField(null=True)),
            ('agreement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name='members', to='pqkds.groupkeyagreement')),
            ('node', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                      related_name='group_agreement_memberships', to='pqkds.node')),
        ], options={'db_table': f'{table_prefix}pqkds_group_agreement_members',
                    'constraints': [
                        models.UniqueConstraint(fields=['agreement', 'node'], name='pqkds_group_member_unique'),
                        models.UniqueConstraint(fields=['agreement', 'participant_node_code'], name='pqkds_group_code_unique')]}),
    ]
