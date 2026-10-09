# -*- coding: utf-8 -*-
"""Add public provenance only; no historical backfill, slots or key bytes changed."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0026_chain_key_binding')]

    operations = [
        migrations.AddField(
            model_name='nodelongtermkey', name='generation_scheme',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='nodelongtermkey', name='generation_scheme_version',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='nodelongtermkey', name='generation_issuance_id',
            field=models.CharField(blank=True, default='', max_length=36),
        ),
        migrations.AddField(
            model_name='nodelongtermkey', name='generation_authorization_ticket_id',
            field=models.CharField(blank=True, default='', max_length=36),
        ),
        migrations.AddField(
            model_name='nodelongtermkey', name='generation_context',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name='KeyGenerationIssuance',
            fields=[
                ('generation_issuance_id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('algorithm', models.CharField(max_length=20)),
                ('key_id', models.CharField(max_length=64)),
                ('key_version', models.PositiveIntegerField()),
                ('context', models.JSONField()),
                ('status', models.CharField(default='ISSUED', max_length=16)),
                ('public_key_hash', models.CharField(blank=True, default='', max_length=64)),
                ('current_slot', models.CharField(default='CURRENT', max_length=8, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='keygen_issuances', to='pqkds.node')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_keygen_issuances',
                'constraints': [models.UniqueConstraint(
                    fields=('node', 'algorithm', 'key_id', 'key_version', 'current_slot'),
                    name='pqkds_keygen_uniq_current',
                )],
            },
        ),
        migrations.CreateModel(
            name='KeyGenerationAuthorization',
            fields=[
                ('authorization_ticket_id', models.CharField(max_length=36, primary_key=True, serialize=False)),
                ('status', models.CharField(default='ISSUED', max_length=16)),
                ('public_key_hash', models.CharField(blank=True, default='', max_length=64)),
                ('current_slot', models.CharField(default='CURRENT', max_length=8, null=True)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('issuance', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name='authorizations', to='pqkds.keygenerationissuance')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_keygen_authorizations',
                'constraints': [models.UniqueConstraint(
                    fields=('issuance', 'current_slot'), name='pqkds_keygen_uniq_auth',
                )],
            },
        ),
    ]
