"""Node public-key outbox routed to the existing Java FISCO account, never Web3/DID.

Persist signed bytes and their hash BEFORE submit. Retries use identical bytes, not a
new nonce. Local ACTIVE and confirmed chain evidence remain independent facts.
"""
import hashlib
import json
import os
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from .chain_backend import is_fabric_did
from .models import ChainKeyBinding, Node

PROVIDER = 'FISCO'
NAMESPACE = 'kms-node-fisco-v1'


def enabled():
    return not is_fabric_did() and os.getenv('KMS_NODE_FISCO_ENABLED', 'false').lower() == 'true'


def chain_id():
    return 'fisco:group-1:' + os.getenv('KMS_NODE_FISCO_CONTRACT_ADDRESS', '').strip().lower()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def snapshot(key):
    material = key.public_key
    digest = hashlib.sha256(material.encode('utf-8')).hexdigest()
    if digest != key.public_key_hash:
        raise ValueError('PUBLIC_HASH_MISMATCH')
    return dict(nodeId=key.node.node_id, algorithm=key.algorithm, keyId=key.key_id,
                keyVersion=str(key.key_version), publicKeyHash=digest,
                publicMaterial=material if len(material.encode('utf-8')) <= 8192 else 'sha256:' + digest)


def enqueue(key):
    if not enabled():
        return None
    if not connection.in_atomic_block:
        raise RuntimeError('FISCO outbox requires the registration transaction')
    Node.objects.select_for_update().get(pk=key.node_id)
    ref = f'node/{key.node.node_id}/{key.algorithm}/{key.key_id}/{key.key_version}'
    metadata = canonical(snapshot(key))
    existing = ChainKeyBinding.objects.select_for_update().filter(
        provider=PROVIDER, chain_id=chain_id(), namespace=NAMESPACE, key_ref=ref,
        event_type='REGISTERED', key_status='REGISTERED').first()
    if existing:
        if existing.metadata != metadata:
            raise ValueError('FISCO_IDEMPOTENCY_CONFLICT')
        return existing
    latest = ChainKeyBinding.objects.select_for_update().filter(node_id=key.node_id).order_by('-sequence').first()
    event_id = hashlib.sha256(canonical([PROVIDER, chain_id(), NAMESPACE, ref]).encode('utf-8')).hexdigest()
    return ChainKeyBinding.objects.create(provider=PROVIDER, chain_id=chain_id(), namespace=NAMESPACE,
        node=key.node, long_term_key=key, node_id_snapshot=key.node.node_id,
        algorithm=key.algorithm, key_id=key.key_id, key_version=key.key_version,
        key_ref=ref, event_type='REGISTERED', key_status='REGISTERED',
        sequence=(latest.sequence if latest else 0) + 1, event_id=event_id,
        metadata=metadata, metadata_digest=hashlib.sha256(metadata.encode('utf-8')).hexdigest(), status='PENDING')


def status(key):
    row = ChainKeyBinding.objects.filter(provider=PROVIDER, chain_id=chain_id(), namespace=NAMESPACE,
                                        long_term_key=key).order_by('-sequence').first()
    return dict(provider=PROVIDER, chainId=chain_id(), status=row.status if row else 'NOT_REGISTERED',
                txId=row.tx_id if row else '', lastError=row.last_error if row else '',
                transactionValid=row.transaction_valid if row else False,
                metadataMatches=row.metadata_matches if row else False,
                blockHeight=row.block_height if row else None,
                chainKeyId=str(int(hashlib.sha256(f'node/{key.node.node_id}/{key.algorithm}/{key.key_id}/{key.key_version}'.encode()).hexdigest(), 16) | (1 << 255)),
                evidenceType='KEY_REGISTRATION', writeEnabled=enabled(),
                confirmedAt=row.confirmed_at.isoformat() if row and row.confirmed_at else None)


def call_java(operation, payload):
    base = os.getenv('KMS_NODE_FISCO_BASE', 'http://updatedel-java:9082').rstrip('/')
    url = urlsplit(base)
    # Configured internal service only; never accepts a target URL from a business request.
    if url.scheme != 'http' or url.hostname != 'updatedel-java' or url.port != 9082 or url.path or url.query or url.fragment or url.username:
        raise ValueError('INVALID_FISCO_INTERNAL_ENDPOINT')
    token = os.getenv('INTERNAL_TOKEN', '')
    if not token:
        raise ValueError('FISCO_INTERNAL_TOKEN_MISSING')
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(base + '/internal/node-fisco/' + operation,
                                json=payload, headers={'X-Internal-Token': token}, timeout=(5, 40), allow_redirects=False)
        response.raise_for_status()
        result = response.json()
    if result.get('chainId') != chain_id() or result.get('publicKeyHash') != payload['publicKeyHash']:
        raise ValueError('FISCO_RESPONSE_IDENTITY_MISMATCH')
    ref = f"node/{payload['nodeId']}/{payload['algorithm']}/{payload['keyId']}/{payload['keyVersion']}"
    expected_id = str(int(hashlib.sha256(ref.encode('utf-8')).hexdigest(), 16) | (1 << 255))
    if result.get('chainKeyId') != expected_id:
        raise ValueError('FISCO_RESPONSE_KEY_MISMATCH')
    return result


def process_one(api=call_java):
    if not enabled():
        return False
    with transaction.atomic():
        row = (ChainKeyBinding.objects.select_for_update().filter(provider=PROVIDER, chain_id=chain_id(), namespace=NAMESPACE,
            status__in=['PENDING', 'PREPARED', 'SUBMITTED', 'PENDING_VERIFICATION', 'NOT_CONFIGURED'])
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=timezone.now())).order_by('id').first())
        if row is None:
            return False
        token = uuid.uuid4().hex
        row.lease_token, row.lease_until = token, timezone.now() + timedelta(seconds=180)
        row.attempts += 1
        row.save(update_fields=['lease_token', 'lease_until', 'attempts'])
    owned = ChainKeyBinding.objects.filter(pk=row.pk, lease_token=token)
    try:
        if not row.long_term_key_id:
            raise ValueError('FISCO_SOURCE_KEY_MISSING')
        if hashlib.sha256(row.metadata.encode('utf-8')).hexdigest() != row.metadata_digest:
            raise ValueError('FISCO_OUTBOX_DIGEST_MISMATCH')
        payload = json.loads(row.metadata)
        if not row.tx_id:
            prepared = api('prepare', payload)
            txid, signed = prepared.get('txId'), prepared.get('signedTransaction')
            import re
            if prepared.get('status') != 'PREPARED' or not re.fullmatch(r'0x[0-9a-fA-F]{64}', txid or '') or not re.fullmatch(r'(?:0x)?[0-9a-fA-F]+', signed or '') or len(signed) > 65536:
                raise ValueError('FISCO_INVALID_PREPARATION')
            # This update commits before any network submission.
            if owned.update(tx_id=txid, nonce=signed, status='PREPARED') != 1:
                return True
            row.tx_id, row.nonce = txid, signed
        payload.update(txId=row.tx_id, signedTransaction=row.nonce)
        result = api('receipt', payload) if row.submit_started else {'status': 'PENDING_VERIFICATION'}
        if result.get('status') == 'PENDING_VERIFICATION':
            if owned.update(status='SUBMITTED', submit_started=True) != 1:
                return True
            result = api('submit', payload)  # Identical signed tx/hash across retries.
        outcome = result.get('status')
        if outcome not in ('CONFIRMED', 'FAILED', 'PENDING_VERIFICATION') or result.get('txId') != row.tx_id:
            raise ValueError('FISCO_INVALID_RECEIPT_RESPONSE')
        values = dict(status=outcome, lease_token='', lease_until=timezone.now() + timedelta(seconds=10),
                      last_error='' if outcome == 'CONFIRMED' else result.get('lastError', 'FISCO_AWAITING_RECEIPT'))
        if outcome == 'CONFIRMED':
            height = str(result.get('blockHeight', ''))
            block = int(height, 16) if height.startswith('0x') else int(height)
            if block < 1:
                raise ValueError('FISCO_INVALID_BLOCK_HEIGHT')
            values.update(transaction_valid=True, metadata_matches=True, confirmed_at=timezone.now(), block_height=block)
        owned.update(**values)
    except Exception as error:
        # Do not print request/response bodies, signed transactions or credentials.
        terminal = isinstance(error, ValueError)
        owned.update(status='FAILED' if terminal else ('PENDING_VERIFICATION' if row.tx_id else 'NOT_CONFIGURED'),
                     last_error=str(error)[:120] if terminal else 'FISCO_ENDPOINT_UNAVAILABLE',
                     lease_token='', lease_until=timezone.now() + timedelta(seconds=30))
    return True
