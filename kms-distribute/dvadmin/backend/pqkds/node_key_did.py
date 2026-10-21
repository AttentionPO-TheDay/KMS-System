"""DID for the actual browser key-registration flow; independent of the FISCO route.

Only requestId/SysPid reach the bridge. The business-key association lives here;
the vendor's on-chain SysPid document metadata remains the SysPid itself.
"""
import os
import re
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .fabric_did_client import BindingError, FabricDidClient
from .models import NodeKeyDidRecord, NodeLongTermKey


def enabled():
    return os.environ.get('FABRIC_DID_NODE_KEYGEN_ENABLED', 'false').lower() == 'true'


def payload(record):
    return {
        'provider': 'FABRIC_DID', 'requestId': str(record.request_id),
        'sysPid': record.sys_pid or '', 'chainId': record.chain_id,
        'did': record.did, 'txId': record.tx_id, 'status': record.status,
        'transactionValid': record.transaction_valid, 'metadataMatches': record.metadata_matches,
        'errorCode': record.last_error or None,
        'createdAt': record.created_at.isoformat(), 'updatedAt': record.updated_at.isoformat(),
    }


def key_payload(key):
    if not enabled():
        return None
    record = NodeKeyDidRecord.objects.filter(key=key).first()
    return payload(record) if record else None


def register(key, client_factory=None):
    if not enabled():
        return {'provider': 'FABRIC_DID', 'status': 'DISABLED', 'sysPid': '',
                'errorCode': 'NODE_KEYGEN_DID_DISABLED'}
    # Concurrent/idempotent registrations serialize on the existing business-key row.
    with transaction.atomic():
        NodeLongTermKey.objects.select_for_update().get(pk=key.pk)
        record, _ = NodeKeyDidRecord.objects.get_or_create(key=key)
    return process(record, submit=True, client_factory=client_factory)


def _identity(data, record, preparing=False):
    configured_chain = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()
    chain = data.get('chainId')
    if (data.get('provider') != 'FABRIC_DID' or not isinstance(chain, str) or not chain
            or len(chain) > 128 or (configured_chain and chain != configured_chain)
            or (record.chain_id and chain != record.chain_id)):
        raise BindingError('DID_RESPONSE_IDENTITY_MISMATCH')
    sys_pid, tx_id, did = (data.get(k) for k in ('sysPid', 'txId', 'did'))
    if (not isinstance(sys_pid, str) or not re.fullmatch('[0-9a-f]{182}', sys_pid)
            or not isinstance(tx_id, str) or not re.fullmatch('[0-9a-f]{64}', tx_id)
            or not isinstance(did, str) or not did.startswith('did:') or len(did) > 512
            or (record.sys_pid and sys_pid != record.sys_pid)
            or (record.tx_id and tx_id != record.tx_id)
            or (record.did and did != record.did)
            or (preparing and data.get('requestId') != str(record.request_id))):
        raise BindingError('DID_RESPONSE_IDENTITY_MISMATCH')
    return dict(sys_pid=sys_pid, tx_id=tx_id, did=did, chain_id=chain)


def process(record, *, submit=False, client_factory=None):
    """Claim briefly, do network I/O outside transactions, fence late responses.

    Once submission starts, all later requests only verify the SAME transaction.
    A lost prepare response can safely be retried using the stored request UUID.
    """
    if not enabled():
        return payload(record)
    token = str(uuid.uuid4())
    with transaction.atomic():
        record = NodeKeyDidRecord.objects.select_for_update().get(pk=record.pk)
        if (submit and record.status == 'CONFIRMED') or (record.lease_expires_at and record.lease_expires_at > timezone.now()):
            return payload(record)
        if not submit and not record.sys_pid:
            return payload(record)
        record.lease_token = token
        record.lease_expires_at = timezone.now() + timedelta(seconds=60)
        record.save(update_fields=['lease_token', 'lease_expires_at'])

    def save(**values):
        changed = NodeKeyDidRecord.objects.filter(pk=record.pk, lease_token=token).update(
            **values, updated_at=timezone.now())
        if not changed:
            raise BindingError('DID_OPERATION_LEASE_EXPIRED')
        for name, value in values.items():
            setattr(record, name, value)

    client = None
    try:
        if not os.environ.get('INTERNAL_TOKEN', '').strip():
            raise BindingError('MISSING_INTERNAL_TOKEN')
        client = (client_factory or FabricDidClient)()
        if not record.sys_pid:
            prepared = client.prepare_sys_pid(record.request_id)
            identity = _identity(prepared, record, preparing=True)
            if prepared.get('status') not in ('PREPARED', 'PENDING_VERIFICATION'):
                raise BindingError('INVALID_DID_PREPARE_RESPONSE')
            save(**identity, status='PREPARED', last_error='',
                 submit_started=prepared.get('submitted') is True or prepared.get('status') == 'PENDING_VERIFICATION')
        if submit and not record.submit_started:
            # Persist uncertainty BEFORE sending. A timeout must never trigger a fresh transaction.
            save(submit_started=True, status='PENDING_VERIFICATION', last_error='')
            data = client.submit_sys_pid(record.sys_pid)
        else:
            data = client.verify_sys_pid(record.sys_pid)
        _identity(data, record)
        state = data.get('status')
        if state not in ('CONFIRMED', 'PENDING_VERIFICATION', 'FAILED'):
            raise BindingError('INVALID_DID_VERIFICATION_RESPONSE')
        valid, matches = data.get('transactionValid'), data.get('metadataMatches')
        if any(value is not None and type(value) is not bool for value in (valid, matches)):
            raise BindingError('INVALID_DID_VERIFICATION_RESPONSE')
        if state == 'CONFIRMED' and (valid is not True or matches is not True):
            raise BindingError('DID_CONFIRMATION_INCOMPLETE')
        error = data.get('errorCode') or ''
        error = error if isinstance(error, str) and re.fullmatch('[A-Z0-9_]{0,80}', error) else 'DID_VERIFICATION_ERROR'
        save(status=state, transaction_valid=valid, metadata_matches=matches, last_error=error)
    except BindingError as exc:
        NodeKeyDidRecord.objects.filter(pk=record.pk, lease_token=token).update(
            status='PENDING_VERIFICATION' if record.submit_started else ('PREPARED' if record.sys_pid else 'PREPARE_FAILED'),
            last_error=exc.code, updated_at=timezone.now())
    finally:
        if client is not None:
            client.close()
        NodeKeyDidRecord.objects.filter(pk=record.pk, lease_token=token).update(lease_token='', lease_expires_at=None)
    record.refresh_from_db()
    return payload(record)
