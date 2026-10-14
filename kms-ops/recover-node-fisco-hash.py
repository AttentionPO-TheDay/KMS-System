#!/usr/bin/env python3
"""Run inside dvadmin3-django via stdin. Query only; --apply repairs confirmed rows.

Never submits a transaction, prepares a new nonce, changes a key or prints signed bytes.
The ECDSA Keccak candidate is accepted ONLY after Java validates the actual receipt.
"""
import argparse
import hashlib
import json
import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from Crypto.Hash import keccak
from django.db import transaction
from django.utils import timezone
from pqkds.models import ChainKeyBinding
from pqkds.node_fisco_evidence import call_java, PROVIDER, NAMESPACE


def recover_one(row, apply=False, api=call_java):
    if row.status != 'FAILED' or row.last_error != 'FISCO_RESPONSE_IDENTITY_MISMATCH':
        raise ValueError('NOT_AFFECTED_ROW')
    if hashlib.sha256(row.metadata.encode('utf-8')).hexdigest() != row.metadata_digest:
        raise ValueError('OUTBOX_DIGEST_MISMATCH')
    signed = row.nonce
    if len(signed) > 65536 or not re.fullmatch(r'(?:0x)?(?:[0-9a-fA-F]{2})+', signed):
        raise ValueError('INVALID_SIGNED_TRANSACTION')
    raw = bytes.fromhex(signed[2:] if signed.startswith('0x') else signed)
    corrected = '0x' + keccak.new(digest_bits=256, data=raw).hexdigest()
    payload = json.loads(row.metadata)
    payload['txId'] = corrected
    result = api('receipt', payload)  # Never prepare/submit; no signed bytes sent.
    ref = f"node/{payload['nodeId']}/{payload['algorithm']}/{payload['keyId']}/{payload['keyVersion']}"
    expected_id = str(int(hashlib.sha256(ref.encode('utf-8')).hexdigest(), 16) | (1 << 255))
    if (result.get('chainId') != row.chain_id or result.get('publicKeyHash') != payload['publicKeyHash']
            or result.get('chainKeyId') != expected_id or result.get('txId') != corrected):
        raise ValueError('RECOVERY_RESPONSE_MISMATCH')
    outcome = result.get('status')
    report = dict(id=row.pk, algorithm=row.algorithm, oldTxId=row.tx_id, txId=corrected,
                  status=outcome, applied=False)
    if outcome != 'CONFIRMED':
        return report  # Unknown or failed receipt never changes the database.
    height = str(result.get('blockHeight', ''))
    block = int(height, 16) if height.startswith('0x') else int(height)
    if block < 1:
        raise ValueError('INVALID_BLOCK_HEIGHT')
    report['blockHeight'] = block
    if apply:
        with transaction.atomic():
            current = ChainKeyBinding.objects.select_for_update().get(pk=row.pk)
            if (current.status != row.status or current.last_error != row.last_error
                    or current.tx_id != row.tx_id or current.nonce != row.nonce
                    or current.metadata_digest != row.metadata_digest):
                raise ValueError('RECOVERY_ROW_CHANGED')
            current.tx_id = corrected
            current.status = 'CONFIRMED'
            current.block_height = block
            current.transaction_valid = current.metadata_matches = True
            current.confirmed_at = timezone.now()
            current.last_error = current.lease_token = ''
            current.lease_until = None
            current.save(update_fields=['tx_id', 'status', 'block_height', 'transaction_valid',
                'metadata_matches', 'confirmed_at', 'last_error', 'lease_token', 'lease_until', 'updated_at'])
        report['applied'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows = ChainKeyBinding.objects.filter(provider=PROVIDER, namespace=NAMESPACE,
        status='FAILED', last_error='FISCO_RESPONSE_IDENTITY_MISMATCH').exclude(tx_id='').order_by('id')
    count = 0
    for row in rows.iterator():
        try:
            report = recover_one(row, args.apply)
            print(json.dumps(report))
            count += int(report['applied'])
        except Exception as error:
            # Never print exception bodies, request metadata, signed transactions or credentials.
            print(json.dumps(dict(id=row.pk, errorType=type(error).__name__, applied=False)))
    print('Confirmed rows repaired: ' + str(count))


if __name__ == '__main__':
    main()
