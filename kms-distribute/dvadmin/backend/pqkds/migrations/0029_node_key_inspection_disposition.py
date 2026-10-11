from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0028_node_key_auto_revocation')]

    operations = [
        migrations.AddField(model_name='nodekeyinspection', name='handled_by',
                            field=models.CharField(max_length=64, blank=True, default='')),
        migrations.AddField(model_name='nodekeyinspection', name='handled_at',
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='nodekeyinspection', name='disposition',
                            field=models.CharField(max_length=20, choices=[
                                ('confirmed', 'confirmed'),
                                ('manual_revoked', 'manual_revoked'),
                                ('dismissed', 'dismissed'),
                                ('rechecked', 'rechecked'),
                            ], null=True, blank=True)),
        migrations.AddField(model_name='nodekeyinspection', name='disposition_note',
                            field=models.TextField(null=True, blank=True)),
        migrations.AlterField(model_name='nodekeyinspection', name='action',
                              field=models.CharField(max_length=20, choices=[
                                  ('PENDING_REVIEW', 'PENDING_REVIEW'),
                                  ('RESOLVED', 'RESOLVED'),
                                  ('AUTO_REVOKED', 'AUTO_REVOKED'),
                                  ('MANUAL_REVOKED', 'MANUAL_REVOKED'),
                              ])),
    ]
