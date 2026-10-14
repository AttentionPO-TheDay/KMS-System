from django.db import migrations, models
from dvadmin.utils.models import table_prefix


def seed_domains(apps, schema_editor):
    Domain = apps.get_model('pqkds', 'Domain')
    Node = apps.get_model('pqkds', 'Node')
    alias = schema_editor.connection.alias
    ids = set(Node.objects.using(alias).exclude(domain_id='').values_list('domain_id', flat=True))
    ids.add('domain-1')
    for domain_id in ids:
        Domain.objects.using(alias).get_or_create(domain_id=domain_id, defaults={'name': domain_id})


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0035_chain_binding_block_height')]
    operations = [
        migrations.CreateModel(name='Domain', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('domain_id', models.CharField(max_length=64, unique=True)),
            ('name', models.CharField(max_length=100)),
            ('description', models.CharField(blank=True, max_length=500)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
        ], options={'db_table': f'{table_prefix}pqkds_domains', 'ordering': ['domain_id']}),
        migrations.RunPython(seed_domains, migrations.RunPython.noop),
    ]
