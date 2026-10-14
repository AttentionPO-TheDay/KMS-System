"""Logical-domain regression, fresh in-memory SQLite only, no key or chain writes."""
import ast
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from importlib import import_module
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from pqkds.models import DistributionBatch, Node, Domain
from django.http import JsonResponse
from django.test import RequestFactory
from django.db import IntegrityError, transaction

# Execute the real pure classification function without initializing crypto/chain clients.
source = Path(__file__).resolve().parents[1] / 'pqkds' / 'distribution_service.py'
definition = next(item for item in ast.parse(source.read_text(encoding='utf-8')).body
                  if isinstance(item, ast.FunctionDef) and item.name == 'classify_distribution')
namespace = {'Tuple': Tuple, 'List': List}
exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), namespace)
classify = namespace['classify_distribution']
with connection.schema_editor() as editor:
    editor.create_model(DistributionBatch)
    editor.create_model(Domain)

# Execute real handlers with explicit identities, without loading network clients.
root = source.parent
domain_def = next(item for item in ast.parse((root / 'domain_views.py').read_text(encoding='utf-8')).body
                  if isinstance(item, ast.FunctionDef) and item.name == 'domains')
domain_def.decorator_list = []
env = dict(Domain=Domain, json=json, JsonResponse=JsonResponse, IntegrityError=IntegrityError, transaction=transaction)
exec(compile(ast.Module(body=[domain_def], type_ignores=[]), 'domain_views.py', 'exec'), env)
domain_handler = env['domains']
admin = {'principalType': 'ADMIN', 'roleLevel': 0, 'userId': 1}


class DomainTests(unittest.TestCase):
    def test_node_create_and_update_require_registered_domain(self):
        from rest_framework import serializers
        tree = ast.parse((root / 'serializers.py').read_text(encoding='utf-8'))
        for name in ('NodeCreateSerializer', 'NodeUpdateSerializer'):
            cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name)
            method = next(item for item in cls.body if isinstance(item, ast.FunctionDef) and item.name == 'validate_domain_id')
            env = {'serializers': serializers, '__package__': 'pqkds'}
            exec(compile(ast.Module(body=[method], type_ignores=[]), 'serializers.py', 'exec'), env)
            validator = env['validate_domain_id']
            Domain.objects.get_or_create(domain_id='registered', defaults={'name': 'Registered'})
            self.assertEqual(validator(None, 'registered'), 'registered')
            with self.assertRaises(serializers.ValidationError):
                validator(None, 'unregistered')

    def test_registry_create_empty_duplicate_validation_and_permissions(self):
        factory = RequestFactory()
        request = factory.post('/domains/', data=json.dumps({'domain_id': 'empty-domain', 'name': '空域'}), content_type='application/json')
        self.assertEqual(domain_handler(request, {'principalType': 'NODE', 'roleLevel': 0}).status_code, 403)
        self.assertEqual(domain_handler(request, {'principalType': 'ADMIN'}).status_code, 403)
        self.assertEqual(domain_handler(RequestFactory().get('/domains/'), {'roleLevel': 0, 'userId': 1}).status_code, 200)
        self.assertEqual(domain_handler(request, admin).status_code, 201)
        self.assertEqual(Node.objects.filter(domain_id='empty-domain').count(), 0)
        self.assertEqual(domain_handler(request, admin).status_code, 409)
        self.assertTrue(any(row['domain_id'] == 'empty-domain' for row in json.loads(domain_handler(factory.get('/domains/'), admin).content)['data']))
        for data in [[], {'domain_id': ''}, {'domain_id': 7, 'name': 'a'}, {'domain_id': 'x' * 65, 'name': 'a'}]:
            bad = factory.post('/domains/', data=json.dumps(data), content_type='application/json')
            self.assertEqual(domain_handler(bad, admin).status_code, 400)

    def test_migration_backfills_existing_memberships_without_changing_nodes(self):
        node = Node.objects.create(node_id='migration-node', name='M', ip_address='127.0.0.1', port=99, domain_id='legacy-domain')
        migration = import_module('pqkds.migrations.0036_domain')
        apps = SimpleNamespace(get_model=lambda app, name: Domain if name == 'Domain' else Node)
        migration.seed_domains(apps, SimpleNamespace(connection=connection))
        migration.seed_domains(apps, SimpleNamespace(connection=connection))
        self.assertEqual(Domain.objects.filter(domain_id='legacy-domain').count(), 1)
        self.assertTrue(Domain.objects.filter(domain_id='domain-1').exists())
        node.refresh_from_db()
        self.assertEqual(node.domain_id, 'legacy-domain')

    def test_admin_batch_projection_is_global_and_node_projection_is_fenced(self):
        tree = ast.parse((root / 'user_distribution_views.py').read_text(encoding='utf-8'))
        definitions = [item for item in tree.body if isinstance(item, ast.FunctionDef)
                       and item.name in ('distribution_batches', '_distribution_admin', '_safe_json_list', '_safe')]
        for item in definitions:
            item.decorator_list = []
        env = dict(DistributionBatch=DistributionBatch, List=List, Any=object, json=json,
                   _ok=lambda data: data, _error=lambda message: {'error': message},
                   logger=SimpleNamespace(warning=lambda *args: None))
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'user_distribution_views.py', 'exec'), env)
        DistributionBatch.objects.create(batch_id='other-owner', user_id=99, wrapping_algorithm='SM2',
            source_domain_id='a', target_domain_ids='["b"]', distribution_type='cross')
        handler = env['distribution_batches']
        request = RequestFactory().get('/distribution-batches/', {'limit': 1, 'page': 1})
        result = handler(request, admin)
        self.assertGreaterEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['batchId'], 'other-owner')
        self.assertEqual(handler(request, {'principalType': 'NODE', 'userId': 8})['total'], 0)

    def test_same_cross_mixed_and_unknown_domains(self):
        node = lambda domain: SimpleNamespace(domain_id=domain)
        self.assertEqual(classify(node('domain-a'), [node('domain-a')])[2], 'same')
        self.assertEqual(classify(node('domain-a'), [node('domain-b')]), ('domain-a', ['domain-b'], 'cross'))
        self.assertEqual(classify(node('domain-a'), [node('domain-b'), node('domain-a')])[2], 'mixed')
        self.assertEqual(classify(node(''), [node('domain-b')])[2], 'mixed')

    def test_changing_membership_preserves_historical_batch_snapshot(self):
        self.assertEqual(connection.settings_dict['NAME'], ':memory:')
        sender = Node.objects.create(node_id='isolated-domain-a', name='A', ip_address='127.0.0.1', port=1, domain_id='domain-a')
        receiver = Node.objects.create(node_id='isolated-domain-b', name='B', ip_address='127.0.0.1', port=2, domain_id='domain-b')
        source_domain, target_domains, kind = classify(sender, [receiver])
        batch = DistributionBatch.objects.create(batch_id='isolated-domain-snapshot', user_id=1,
            wrapping_algorithm='SM2', node_ids=json.dumps([receiver.id]), status='pending',
            source_domain_id=source_domain, target_domain_ids=json.dumps(target_domains), distribution_type=kind)
        Node.objects.filter(pk=receiver.pk).update(domain_id='domain-a')
        receiver.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(classify(sender, [receiver])[2], 'same')
        self.assertEqual(batch.distribution_type, 'cross')
        self.assertEqual(json.loads(batch.target_domain_ids), ['domain-b'])


if __name__ == '__main__':
    unittest.main()
