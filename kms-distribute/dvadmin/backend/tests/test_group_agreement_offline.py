"""Actual Django models/service in fresh :memory: SQLite; no production settings/network.
Does not claim to exercise MySQL's select_for_update concurrency semantics.
"""
import ast
import base64
import importlib
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.apps import apps
from django.db import connection, IntegrityError, transaction
from django.db.migrations.state import ProjectState
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone
from pqkds import group_agreement_service as service
from pqkds.models import (Node, NodeLongTermKey, SessionKey, UserNodeAuthorization,
                          GroupKeyAgreement, GroupAgreementMember)

# Apply the actual additive migration to a schema containing the existing Node model.
state = ProjectState.from_apps(apps)
state.remove_model('pqkds', 'groupagreementmember')
state.remove_model('pqkds', 'groupkeyagreement')
with connection.schema_editor() as editor:
    editor.create_model(SessionKey)
    editor.create_model(UserNodeAuthorization)
    migration = importlib.import_module('pqkds.migrations.0037_group_key_agreement').Migration('0037', 'pqkds')
    for operation in migration.operations:
        previous = state.clone()
        operation.state_forwards('pqkds', state)
        operation.database_forwards('pqkds', editor, previous, state)

# Real handlers with explicit identities; auth transport is covered by existing tests.
tree = ast.parse((Path(__file__).resolve().parents[1] / 'pqkds/group_agreement_views.py').read_text(encoding='utf-8'))
definitions = [item for item in tree.body if isinstance(item, ast.FunctionDef)]
for definition in definitions:
    definition.decorator_list = []
env = {'service': service, 'json': json, 'JsonResponse': JsonResponse}
exec(compile(ast.Module(body=definitions, type_ignores=[]), 'group_agreement_views.py', 'exec'), env)


class GroupTests(unittest.TestCase):
    sequence = 0

    def setUp(self):
        GroupTests.sequence += 1
        prefix = GroupTests.sequence
        self.nodes = [Node.objects.create(node_id=f'{prefix}-{letter}', name=letter, ip_address='127.0.0.1',
                                          port=99, sys_user_id=prefix * 10 + index, status='active')
                      for index, letter in enumerate('ABCD', 1)]
        self.channels = []
        for node in self.nodes:
            for algorithm in ('SM2', 'FALCON'):
                NodeLongTermKey.objects.create(node=node, key_id=f'{node.node_id}-{algorithm}', key_version=1,
                    algorithm=algorithm, status='ACTIVE', public_key='04' + '11' * 64,
                    public_key_hash='f' * 64, expires_at=timezone.now() + timedelta(hours=1))
        for index, left in enumerate(self.nodes[:3]):
            for right in self.nodes[index + 1:3]:
                UserNodeAuthorization.objects.create(user_id=left.sys_user_id, node=right, status='active')
                self.channels.append(SessionKey.objects.create(session_id=f'{left.node_id}-{right.node_id}',
                    node1=left, node2=right, status='established', session_type='gm_sm2',
                    recipient_key_id=f'{right.node_id}-SM2', recipient_key_version=1,
                    falcon_key_id=f'{left.node_id}-FALCON', falcon_key_version=1,
                    expires_at=timezone.now() + timedelta(hours=1)))
        self.group = service.create(self.nodes[0], {'participantNodeIds': [n.node_id for n in self.nodes[1:3]]})
        self.gid = self.group['agreementId']

    def act(self, node, action, payload):
        return service.operate(self.gid, node, action, payload)

    def commit_all(self):
        for index, node in enumerate(self.nodes[:3], 1):
            result = self.act(node, 'commit', {'commitment': str(index) * 64})
        return result

    def packets(self, sender):
        return [{'toNodeId': n.node_id,
                 'channelSessionId': next(s.session_id for s in self.channels if {s.node1_id, s.node2_id} == {sender.id, n.id}),
                 'iv': base64.b64encode(b'i' * 12).decode(),
                 'ciphertext': base64.b64encode(b'c' * 48).decode()}
                for n in self.nodes[:3] if n.id != sender.id]

    def exchange_all(self):
        self.commit_all()
        for node in self.nodes[:3]:
            result = self.act(node, 'exchange', {'packets': self.packets(node)})
        return result

    def test_real_migration_and_scope_hash(self):
        model_state = ProjectState.from_apps(apps)
        for name in ('groupkeyagreement', 'groupagreementmember'):
            migrated = state.models[('pqkds', name)]
            actual = model_state.models[('pqkds', name)]
            self.assertEqual(migrated.fields.keys(), actual.fields.keys())
            for key in actual.fields:
                self.assertEqual(migrated.fields[key].deconstruct(), actual.fields[key].deconstruct())
            self.assertEqual(migrated.options, actual.options)
        group = GroupKeyAgreement.objects.get(agreement_id=self.gid)
        self.assertEqual(group.scope_hash, service.digest(service.scope(group)))
        self.assertEqual(group.members.count(), 3)

    def test_three_rounds_require_every_member(self):
        self.assertEqual(self.group['status'], 'committing')
        self.assertEqual(self.commit_all()['status'], 'exchanging')
        for node in self.nodes[:2]:
            self.assertEqual(self.act(node, 'exchange', {'packets': self.packets(node)})['status'], 'exchanging')
        data = self.act(self.nodes[2], 'exchange', {'packets': self.packets(self.nodes[2])})
        for node in self.nodes[:2]:
            result = self.act(node, 'confirm', {'proof': 'a' * 64, 'transcriptHash': data['transcriptHash']})
            self.assertEqual(result['status'], 'confirming')
        result = self.act(self.nodes[2], 'confirm', {'proof': 'a' * 64, 'transcriptHash': data['transcriptHash']})
        self.assertEqual((result['status'], result['confirmedCount']), ('established', 3))

    def test_mismatched_confirmations_fail_and_cannot_be_repaired(self):
        data = self.exchange_all()
        for index, node in enumerate(self.nodes[:3]):
            result = self.act(node, 'confirm', {'proof': ('a' if index < 2 else 'b') * 64, 'transcriptHash': data['transcriptHash']})
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.act(self.nodes[2], 'confirm', {'proof': 'a' * 64})['status'], 'failed')

    def test_no_phase_skipping_or_partial_packet_set(self):
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'exchange', {'packets': self.packets(self.nodes[0])})
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'confirm', {'proof': 'a' * 64, 'transcriptHash': ''})
        self.commit_all()
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'exchange', {'packets': self.packets(self.nodes[0])[:1]})

    def test_commits_are_immutable_and_retries_idempotent(self):
        payload = {'commitment': 'a' * 64}
        self.act(self.nodes[0], 'commit', payload)
        first = service.detail(self.gid, self.nodes[0])
        self.assertEqual(first, self.act(self.nodes[0], 'commit', payload))
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'commit', {'commitment': 'b' * 64})

    def test_packets_immutable_wrong_channel_recipient_and_size_rejected(self):
        self.commit_all()
        packets = self.packets(self.nodes[0])
        for key, value in [('channelSessionId', 'other-session'), ('ciphertext', 'AA=='), ('toNodeId', self.nodes[3].node_id)]:
            bad = json.loads(json.dumps(packets)); bad[0][key] = value
            with self.assertRaises(service.AgreementError):
                self.act(self.nodes[0], 'exchange', {'packets': bad})
        self.act(self.nodes[0], 'exchange', {'packets': packets})
        retry = self.act(self.nodes[0], 'exchange', {'packets': packets})
        self.assertEqual(retry['exchangedCount'], 1)
        packets[0]['iv'] = base64.b64encode(b'j' * 12).decode()
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'exchange', {'packets': packets})

    def test_non_members_and_admin_cannot_participate(self):
        with self.assertRaises(service.AgreementError):
            service.detail(self.gid, self.nodes[3])
        for identity in ({'principalType': 'ADMIN', 'userId': self.nodes[0].sys_user_id}, {'principalType': 'NODE', 'userId': -1}):
            with self.assertRaises(service.AgreementError):
                service.actor(identity)
        self.assertEqual(service.listing(self.nodes[3]), [])

    def test_only_recipient_inbox_visible_no_proofs_or_plaintext(self):
        data = self.exchange_all()
        self.assertEqual(len(data['inbox']), 2)
        self.assertTrue(all(packet['toNodeId'] == self.nodes[2].node_id for packet in data['inbox']))
        self.act(self.nodes[2], 'confirm', {'proof': 'a' * 64, 'transcriptHash': data['transcriptHash']})
        for node in self.nodes[:3]:
            response = service.detail(self.gid, node)
            self.assertFalse(any('proof' in member or 'packets' in member for member in response['members']))
            self.assertNotIn('inbox', service.listing(node)[0])

    def test_close_is_terminal_for_every_participant(self):
        self.assertEqual(self.act(self.nodes[1], 'close', {})['status'], 'closed')
        self.assertEqual(self.act(self.nodes[0], 'commit', {'commitment': 'a' * 64})['status'], 'closed')

    def test_expiry_and_base_channel_invalidation(self):
        GroupKeyAgreement.objects.filter(agreement_id=self.gid).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(service.detail(self.gid, self.nodes[0])['status'], 'expired')
        other = service.create(self.nodes[0], {'participantNodeIds': [n.node_id for n in self.nodes[1:3]]})
        SessionKey.objects.filter(pk=self.channels[0].pk).update(status='closed')
        self.assertEqual(service.detail(other['agreementId'], self.nodes[0])['status'], 'failed')

    def test_key_revocation_and_authorization_revocation_gate_access(self):
        NodeLongTermKey.objects.filter(node=self.nodes[0], algorithm='FALCON').update(status='REVOKED', active_slot=None)
        self.assertEqual(service.detail(self.gid, self.nodes[0])['status'], 'failed')
        with self.assertRaises(service.AgreementError):
            service.create(self.nodes[0], {'participantNodeIds': [n.node_id for n in self.nodes[1:3]]})

    def test_current_authorization_required(self):
        UserNodeAuthorization.objects.filter(user_id=self.nodes[0].sys_user_id).update(status='revoked')
        self.assertEqual(service.detail(self.gid, self.nodes[1])['status'], 'failed')

    def test_removed_participants_keep_history_but_invalidate_agreement(self):
        self.exchange_all()
        group = GroupKeyAgreement.objects.get(agreement_id=self.gid)
        group.members.filter(node=self.nodes[2]).update(node=None)
        response = service.detail(self.gid, self.nodes[0])
        self.assertEqual(response['status'], 'failed')
        self.assertEqual(len(response['members']), 3)
        self.assertEqual(response['inbox'], [])

    def test_proof_retry_immutable_and_idempotent(self):
        data = self.exchange_all()
        payload = {'proof': 'a' * 64, 'transcriptHash': data['transcriptHash']}
        response = self.act(self.nodes[0], 'confirm', payload)
        self.assertEqual(response, self.act(self.nodes[0], 'confirm', payload))
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'confirm', {**payload, 'proof': 'b' * 64})
        self.assertEqual(service.detail(self.gid, self.nodes[0])['confirmedCount'], 1)

    def test_duplicate_member_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GroupAgreementMember.objects.create(agreement=GroupKeyAgreement.objects.get(agreement_id=self.gid), node=self.nodes[0])

    def test_creation_rejects_invalid_roster_and_unconnected_nodes(self):
        for ids in ([self.nodes[1].node_id], [self.nodes[1].node_id] * 2, [self.nodes[0].node_id, self.nodes[1].node_id],
                    [self.nodes[1].node_id, self.nodes[3].node_id], [1, 2]):
            with self.assertRaises(service.AgreementError):
                service.create(self.nodes[0], {'participantNodeIds': ids})

    def test_handler_rejects_plaintext_fields_and_bad_json(self):
        factory = RequestFactory()
        identity = {'principalType': 'NODE', 'userId': self.nodes[0].sys_user_id}
        for body in ('[]', '{broken', json.dumps({'participantNodeIds': [], 'secret': 'plaintext'})):
            response = env['agreements'](factory.post('/', data=body, content_type='application/json'), identity)
            self.assertEqual(json.loads(response.content)['code'], 400)
        response = env['agreement'](factory.post('/', data=json.dumps({'action': 'commit', 'commitment': 'a' * 64, 'proof': 'b' * 64}),
                                        content_type='application/json'), self.gid, identity)
        self.assertEqual(json.loads(response.content)['code'], 400)

    def test_wrong_transcript_never_confirms(self):
        self.exchange_all()
        with self.assertRaises(service.AgreementError):
            self.act(self.nodes[0], 'confirm', {'proof': 'a' * 64, 'transcriptHash': 'f' * 64})
        self.assertEqual(service.detail(self.gid, self.nodes[0])['confirmedCount'], 0)


if __name__ == '__main__':
    unittest.main()
