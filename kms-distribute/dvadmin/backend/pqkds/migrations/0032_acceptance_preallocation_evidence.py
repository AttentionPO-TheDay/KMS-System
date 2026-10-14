from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0031_falcon_cl_public_binding')]

    operations = [
        migrations.CreateModel(
            name='AcceptancePreallocationEvidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pool_id', models.CharField(max_length=64, unique=True)),
                ('requested', models.PositiveIntegerField()),
                ('generated', models.PositiveIntegerField()),
                ('failed', models.PositiveIntegerField()),
                ('local_ms', models.FloatField()),
                ('local_throughput', models.FloatField()),
                ('server_ms', models.FloatField(default=0)),
                ('server_throughput', models.FloatField(default=0)),
                ('measured_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name='preallocation_acceptance_evidence', to='pqkds.node')),
                ('target_node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                  related_name='received_preallocation_acceptance_evidence', to='pqkds.node')),
            ],
            options={
                'db_table': 'dvadmin_pqkds_acceptance_preallocation_evidence',
                'ordering': ['-measured_at', '-id'],
                'indexes': [models.Index(fields=['node', '-measured_at'], name='pqkds_accept_prealloc_node')],
            },
        ),
    ]
