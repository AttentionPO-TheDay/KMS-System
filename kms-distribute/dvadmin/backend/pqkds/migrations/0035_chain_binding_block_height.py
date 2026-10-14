from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pqkds', '0034_node_key_auto_update')]
    operations = [migrations.AddField(model_name='chainkeybinding', name='block_height',
                                     field=models.PositiveBigIntegerField(null=True, blank=True))]
