"""Run inside the isolated staging container, never migrate the live database."""
import base64
import hashlib
import json
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
sys.path.insert(0, '/backend')
import django
django.setup()

from django.db import connection, transaction
from django.test import RequestFactory
from pqkds.acceptance_revoke import isolated_tables
from pqkds.crypto_utils import KyberCrypto
from pqkds.models import Node, NodeLongTermKey, PreDistributedKey, LatticePreparation, LatticeTestRecord, KeyDistributionLog
from pqkds import lattice_preallocation as service
from pqkds import lattice_preallocation_math as lattice
from pqkds.lattice_test_views import internal_lattice_tests


def temp_model(model):
    fields = []
    quote = connection.ops.quote_name
    for field in model._meta.local_fields:
        spec = quote(field.column) + ' ' + field.db_type(connection)
        spec += ' NULL' if field.null else ' NOT NULL'
        if field.primary_key: spec += ' PRIMARY KEY'
        fields.append(spec)
    with connection.cursor() as cursor:
        cursor.execute('CREATE TEMPORARY TABLE ' + quote(model._meta.db_table) + ' (' + ','.join(fields) + ') ENGINE=InnoDB')


factory = RequestFactory()
owner = hashlib.sha256(b'lattice-staging-session').hexdigest()
def rpc(body=None, token=True):
    headers = dict(HTTP_X_ACCEPTANCE_OWNER=owner)
    if token: headers['HTTP_X_INTERNAL_TOKEN'] = os.environ['INTERNAL_TOKEN']
    request = factory.get('/', **headers) if body is None else factory.post('/', json.dumps(body), content_type='application/json', **headers)
    response = internal_lattice_tests(request)
    return response.status_code, json.loads(response.content)


production_before = (Node.objects.count(), PreDistributedKey.objects.count())
with isolated_tables((Node, NodeLongTermKey, PreDistributedKey, KeyDistributionLog)):
    with connection.cursor() as cursor:
        columns = [field.name for field in connection.introspection.get_table_description(cursor, PreDistributedKey._meta.db_table)]
        if 'lattice_preparation_id' not in columns:
            cursor.execute('ALTER TABLE ' + connection.ops.quote_name(PreDistributedKey._meta.db_table) + ' ADD COLUMN lattice_preparation_id char(32) NULL')
    temp_model(LatticePreparation)
    temp_model(LatticeTestRecord)
    kem = KyberCrypto(768)
    public, secret = kem.generate_keypair()
    node = Node.objects.create(node_id='lattice-staging-node', name='格预分配隔离测试节点',
        ip_address='127.0.0.1', port=0, status='ACTIVE', kyber_public_key=base64.b64encode(public).decode())
    NodeLongTermKey.objects.create(node=node, algorithm='KYBER', key_id='lattice-staging-kyber', key_version=1,
        public_key=public.hex(), public_key_hash=hashlib.sha256(public.hex().encode()).hexdigest(), status='ACTIVE', active_slot='KYBER')
    assert rpc(token=False)[0] == 403
    assert rpc({'caseId': 'offline-trapdoor', 'passed': True})[0] == 400
    code, root = rpc({'caseId': 'offline-trapdoor'})
    assert code == 200, root
    root = root['data']; assert root['passed']
    code, child = rpc({'caseId': 'basis-delegation', 'rootId': root['preparation']['id'], 'nodeId': node.node_id})
    assert code == 200, child
    child = child['data']; assert child['passed']
    request = dict(caseId='parallel-sampling', preparationId=child['preparation']['id'], count=32, workers=4)
    code, result = rpc(request)
    assert code == 200, result
    result = result['data']; assert result['passed'], result['checks']
    assert result['cleanupComplete'] and PreDistributedKey.objects.count() == 0
    # Independent public-only evidence check and actual receiver-side recovery.
    import numpy as np
    from pqkds.sm4_crypto import SM4Crypto, PayloadCipher
    matrix = np.asarray(result['publicMatrix'], dtype=np.int64)
    for sample in result['samples']:
        message = sample['message'].encode('utf-8')
        assert hashlib.sha256(message).hexdigest() == sample['packageDigest']
        vector = np.asarray(sample['vector'], dtype=np.int64)
        assert np.array_equal(matrix @ vector % lattice.Q, lattice.target_for(message))
        assert np.linalg.norm(vector) <= sample['bound']
        package = json.loads(message)
        shared = kem.decrypt(base64.b64decode(package['kem_ciphertext']), secret)
        key = SM4Crypto.decrypt(base64.b64decode(package['encrypted_aes_key']),
            PayloadCipher.kek_from_shared_secret('sm4', shared), base64.b64decode(package['nonce']) + base64.b64decode(package['tag']))
        assert hashlib.sha256(key).hexdigest() == sample['keyHash']
    # Exercise the real upload view: real Falcon signatures, registered keys,
    # actual writes and lattice batching. Only the external authorization lookup
    # is stubbed to represent a previously approved peer relationship.
    import inspect as pyinspect
    from unittest.mock import patch
    from pqkds.crypto_utils import FalconCrypto
    from pqkds.envelope_signature import node_canonical_payload
    from pqkds.node_self_views import node_pool_preallocate
    from pqkds.key_pool_service import KeyPoolService
    sender = Node.objects.create(node_id='lattice-upload-sender', name='隔离发送节点',
        sys_user_id=999000, ip_address='127.0.0.1', port=0, status='ACTIVE')
    falcon = FalconCrypto(512)
    sign_public, sign_secret = falcon.generate_keypair()
    NodeLongTermKey.objects.create(node=sender, algorithm='FALCON', key_id='lattice-upload-falcon', key_version=1,
        public_key=sign_public.hex(), public_key_hash=hashlib.sha256(sign_public.hex().encode()).hexdigest(), status='ACTIVE', active_slot='FALCON')
    from datetime import timedelta
    from django.utils import timezone
    expiry = (timezone.now() + timedelta(hours=1)).isoformat()
    pool = 'pool_' + 'a' * 32
    items = []
    for sample in result['samples'][:4]:
        envelope = json.loads(sample['message'])
        envelope.update(batch_id=pool, sender_node_id=sender.node_id, receiver_node_id=node.node_id,
            wrapping_algorithm='kyber_kem', recipient_key_id='lattice-staging-kyber', recipient_key_version=1,
            expires_at=expiry, ciphertext_digest=sample['packageDigest'])
        signature = base64.b64encode(falcon.sign(node_canonical_payload(envelope), sign_secret)).decode()
        items.append(dict(envelope=envelope, signature=signature, keyHash=sample['keyHash']))
    payload = dict(targetNodeCode=node.node_id, poolId=pool, expiresAt=expiry, items=items,
                   falconKeyId='lattice-upload-falcon', falconKeyVersion=1)
    request = factory.post('/', json.dumps(payload), content_type='application/json')
    with patch('pqkds.distribution_service.authorized_node_ids', return_value=[node.pk]), transaction.atomic():
        response = pyinspect.unwrap(node_pool_preallocate)(request, {'userId': 999000})
    upload = json.loads(response.content)
    assert response.status_code == 200 and upload['data']['generated'] == 4, upload
    assert upload['data']['lattice']['verified'] == 4
    stored = list(PreDistributedKey.objects.filter(pool_id=pool).order_by('key_index'))
    assert len(stored) == 4 and all(service.verify_pool_row(row) for row in stored)
    broken = json.loads(stored[0].encrypted_key_data)
    original = stored[0].encrypted_key_data
    broken.pop('latticeProof')
    stored[0].encrypted_key_data = json.dumps(broken); stored[0].save(update_fields=['encrypted_key_data'])
    rejection = KeyPoolService.consume_key(sender.node_id, node.node_id, 'kyber_kem', pool_id=pool)
    assert not rejection['success'], rejection
    stored[0].encrypted_key_data = original; stored[0].save(update_fields=['encrypted_key_data'])
    selection = KeyPoolService.consume_key(sender.node_id, node.node_id, 'kyber_kem', pool_id=pool)
    assert selection['success'], selection
    code, history = rpc(); assert code == 200
    assert len(history['data']['records']) == 3
    private_names = {'encrypted_secret', 'basis', 'r', 'falcon_sk'}
    def inspect(value):
        if isinstance(value, dict):
            assert not private_names.intersection(value)
            for nested in value.values(): inspect(nested)
        elif isinstance(value, list):
            for nested in value: inspect(nested)
    inspect(history)
    output = dict(verified=True, root=root['preparation'], delegated=child['preparation'],
        samples=result['valid'], sampleMs=result['samplingMs'], totalMs=result['totalMs'],
        allRecovered=True, checks=result['checks'], historyRecords=3, publicEvidenceVerified=True,
        productionUntouched=True)
    output.update(realNodeUploadVerified=True, realFalconSignatures=4, missingProofRejected=True)
    with open('/tmp/lattice-django-result.json', 'w') as f: json.dump(output, f, ensure_ascii=False, indent=2)
assert (Node.objects.count(), PreDistributedKey.objects.count()) == production_before
print(json.dumps(output, ensure_ascii=False))
