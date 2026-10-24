"""Run the deployed endpoint with real crypto/MySQL; roll back all test rows."""
import base64
from datetime import timedelta
import hashlib
import json
import os
import uuid

from django.db import connection, transaction
from django.test import RequestFactory
from django.utils import timezone

from pqkds.crypto_utils import FalconCrypto, KyberCrypto
from pqkds.envelope_signature import node_canonical_payload
from pqkds.models import Node, NodeLongTermKey, PreDistributedKey, UserNodeAuthorization
from pqkds.node_self_views import node_pool_preallocate
from pqkds.wrappers import wrap_with_public_key, open_node_envelope


def main():
    assert connection.vendor == 'mysql', 'Expected production MySQL constraints'
    suffix = uuid.uuid4().hex
    user_id = -int(suffix[:12], 16)
    pool_id = 'pool_' + suffix
    factory = RequestFactory()
    falcon = FalconCrypto(512)
    falcon_pk, falcon_sk = falcon.generate_keypair()
    kyber_pk, kyber_sk = KyberCrypto(512).generate_keypair()
    kyber_public = base64.b64encode(kyber_pk).decode()
    reports = []
    with transaction.atomic():
        sender = Node.objects.create(node_id='chunk-check-s-' + suffix, name='Upload verification sender',
                                     sys_user_id=user_id, ip_address='127.0.0.1', port=1)
        receiver = Node.objects.create(node_id='chunk-check-r-' + suffix, name='Upload verification receiver',
                                       ip_address='127.0.0.2', port=2)
        for node, algorithm, public in [(sender, 'FALCON', falcon_pk.hex()), (receiver, 'KYBER', kyber_public)]:
            NodeLongTermKey.objects.create(node=node, algorithm=algorithm, key_id='chunk-check-' + algorithm,
                key_version=1, status='ACTIVE', public_key=public,
                public_key_hash=hashlib.sha256(public.encode()).hexdigest(), security_level='512')
        UserNodeAuthorization.objects.create(user_id=user_id, node=receiver, status='active')
        expires = (timezone.now() + timedelta(hours=1)).isoformat()

        def upload(start, items):
            payload = dict(targetNodeCode=receiver.node_id, poolId=pool_id, startIndex=start,
                expiresAt=expires, items=items, falconKeyId='chunk-check-FALCON', falconKeyVersion=1)
            request = factory.post('/api/pqkds/node-self/pool/preallocate/', data=json.dumps(payload),
                                   content_type='application/json')
            request.kms_identity = {'entryMode': 'DEMO', 'userId': user_id}
            response = node_pool_preallocate(request)
            body = json.loads(response.content)
            assert response.status_code == 200, (response.status_code, body)
            return body['data']

        first_chunk = None
        for start in range(0, 2000, 200):
            items = []
            for index in range(start, start + 200):
                key = os.urandom(16)
                envelope, key_hash = wrap_with_public_key(key, kyber_public, 'kyber_kem')
                if index % 200 in (0, 199):
                    assert open_node_envelope(envelope, base64.b64encode(kyber_sk).decode()) == key
                digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, ensure_ascii=False,
                                                   separators=(',', ':')).encode()).hexdigest()
                envelope.update(batch_id=pool_id, sender_node_id=sender.node_id,
                    receiver_node_id=receiver.node_id, recipient_key_id='chunk-check-KYBER',
                    recipient_key_version=1, key_hash=key_hash, ciphertext_digest=digest, expires_at=expires)
                signature = base64.b64encode(falcon.sign(node_canonical_payload(envelope), falcon_sk)).decode()
                items.append(dict(envelope=envelope, keyHash=key_hash, signature=signature))
            result = upload(start, items)
            assert result['generated'] == 200 and result['failed'] == [], result
            assert result['startIndex'] == start
            reports.append(dict(startIndex=start, generated=result['generated'], failed=len(result['failed'])))
            if start == 0:
                first_chunk = items
            print('CHUNK_OK ' + str(start), flush=True)
        indices = list(PreDistributedKey.objects.filter(pool_id=pool_id).order_by('key_index')
                       .values_list('key_index', flat=True))
        assert indices == list(range(2000))
        retry = upload(0, first_chunk)
        assert retry['generated'] == 0 and len(retry['failed']) == 200
        assert all(x['errorCode'] == 'DUPLICATE_ITEM' for x in retry['failed'])
        assert PreDistributedKey.objects.filter(pool_id=pool_id).count() == 2000
        transaction.set_rollback(True)
    assert not Node.objects.filter(node_id__in=[sender.node_id, receiver.node_id]).exists()
    assert not PreDistributedKey.objects.filter(pool_id=pool_id).exists()
    print('VERIFIED ' + json.dumps(dict(database='mysql', requested=2000, stored=2000,
        uniqueIndices=2000, firstIndex=0, lastIndex=1999, chunks=reports,
        duplicateRetryRejected=200, realFalconSignatures=True, realKyberSm4Envelopes=True,
        testRowsRolledBack=True)), flush=True)


main()
