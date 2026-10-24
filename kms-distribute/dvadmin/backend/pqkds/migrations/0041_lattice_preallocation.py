import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0038_nodekeydidrecord')]
    operations = [
        migrations.CreateModel(name='LatticePreparation', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('kind', models.CharField(max_length=16)),
            ('public_matrix', models.JSONField()),
            ('public_digest', models.CharField(max_length=64)),
            ('norm_bound', models.FloatField()),
            ('encrypted_secret', models.TextField()),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ('parent', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='delegations', to='pqkds.latticepreparation')),
            ('node', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lattice_preparations', to='pqkds.node')),
        ], options={'db_table': 'dvadmin_pqkds_lattice_preparation', 'constraints': [models.UniqueConstraint(fields=('parent', 'node'), name='pqkds_lattice_node_root')]}),
        migrations.CreateModel(name='LatticeTestRecord', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('owner', models.CharField(max_length=64, db_index=True)),
            ('case_id', models.CharField(max_length=32)),
            ('result', models.JSONField()),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
        ], options={'db_table': 'dvadmin_pqkds_lattice_test_record'}),
        migrations.AddField(model_name='predistributedkey', name='lattice_preparation',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='pool_items', to='pqkds.latticepreparation')),
    ]
