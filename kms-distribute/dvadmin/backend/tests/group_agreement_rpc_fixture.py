"""STDIN-only isolated browser QA bridge. Explicitly uses fresh offline SQLite.
No HTTP listener, production settings, external network, real accounts or key writes.
"""
import base64
import importlib.util
import json
from pathlib import Path
import secrets
import sys

path = Path(__file__).with_name('test_group_agreement_offline.py')
spec = importlib.util.spec_from_file_location('offline_group_tests', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from django.conf import settings
settings.USE_TZ = True
test = module.GroupTests('test_three_rounds_require_every_member')
test.setUp()
service = module.service
nodes = {node.node_id: node for node in test.nodes[:3]}
channel_secrets = {channel.session_id: secrets.token_hex(16) for channel in test.channels}


def handle(command):
    if command['op'] == 'init':
        return {'nodes': [{'nodeId': n.node_id, 'name': n.name} for n in nodes.values()],
                'channels': [{'left': s.node1.node_id, 'right': s.node2.node_id,
                              'sessionId': s.session_id, 'secret': channel_secrets[s.session_id]} for s in test.channels]}
    node = nodes[command['nodeId']]
    op, payload = command['op'], command.get('payload', {})
    if op == 'list':
        return {'selfNodeId': node.node_id, 'peers': service.peers(node), 'items': service.listing(node)}
    if op == 'create':
        return service.create(node, payload)
    if op == 'detail':
        return service.detail(command['agreementId'], node)
    if op == 'act':
        return service.operate(command['agreementId'], node, payload['action'],
                               {key: value for key, value in payload.items() if key != 'action'})
    if op == 'tamper':
        group = module.GroupKeyAgreement.objects.get(agreement_id=command['agreementId'])
        member = group.members.exclude(node=node).first()
        packets = member.packets
        packet = next(packet for packet in packets if packet['toNodeId'] == node.node_id)
        ciphertext = bytearray(base64.b64decode(packet['ciphertext'])); ciphertext[0] ^= 1
        packet['ciphertext'] = base64.b64encode(ciphertext).decode()
        member.save(update_fields=['packets'])
        return True
    raise ValueError('Unsupported fixture operation')


for line in sys.stdin:
    try:
        command = json.loads(line)
        response = {'id': command['id'], 'result': handle(command)}
    except Exception as exc:
        response = {'id': command.get('id'), 'error': str(exc)}
    print(json.dumps(response, ensure_ascii=False), flush=True)
