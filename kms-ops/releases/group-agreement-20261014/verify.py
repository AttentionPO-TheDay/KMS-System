from django.db import connection
from django.urls import resolve
from django.db.migrations.recorder import MigrationRecorder
from pqkds.models import GroupKeyAgreement, GroupAgreementMember, Node

assert MigrationRecorder.Migration.objects.filter(app='pqkds', name='0037_group_key_agreement').exists()
tables = connection.introspection.table_names()
assert GroupKeyAgreement._meta.db_table in tables
assert GroupAgreementMember._meta.db_table in tables
assert resolve('/api/pqkds/node-self/group-agreements/').url_name == 'node-group-agreements'
print('Migration, MySQL tables and agreement route: OK')
print('Existing nodes:', Node.objects.count())
