"""Backfill only the verified A/SSCL v2 event; never rotate keys or modify SQL rows.

Default is read-only. --submit appends the real missing event after scanning for
an existing matching receipt, so an interrupted run can be resumed safely.
"""
import argparse
import json
import os
import sys
import pymysql
import requests

sys.path.insert(0, '/backend')
CONTRACT = '0x1a61f0b42915fa8e25dbfd111e3db2c5c725bcb0'
TOPIC = '0x22de73619d629ec7133d447cdf4518a474ff2e04167d013fe27d8ae0022716b0'
HASH = '459b521f46942677ffdd080692ca32a0bdada9126e6eab8744a71ae08e8efbfe'
http = requests.Session()


def snapshot():
    db = pymysql.connect(host=os.getenv('DATABASE_HOST', 'mysql'),
                         port=int(os.getenv('DATABASE_PORT', '3306')),
                         user=os.getenv('DATABASE_USER', 'root'),
                         password=os.getenv('DATABASE_PASSWORD', ''),
                         database=os.getenv('DATABASE_NAME', 'falcon_kds'),
                         cursorclass=pymysql.cursors.DictCursor)
    try:
        with db.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            cursor.execute('''SELECT k.id,n.node_id AS node_code,k.algorithm,k.key_id,
                k.key_version,k.status,k.public_key_hash,k.effective_at
                FROM dvadmin_pqkds_node_long_term_keys k
                JOIN dvadmin_pqkds_nodes n ON n.id=k.node_id
                WHERE k.key_id=%s ORDER BY k.key_version''', ('A-SSCL-4cfab58e',))
            rows = cursor.fetchall()
        db.rollback()
        assert len(rows) == 2, 'Unexpected number of versions; stop for review'
        row = rows[1]
        assert (row['id'], row['node_code'], row['algorithm'], row['key_version'], row['status'],
                row['public_key_hash']) == (37, 'A', 'SSCL', 2, 'ACTIVE', HASH), 'Target changed; stop for review'
        assert rows[0]['key_version'] == 1 and rows[0]['status'] == 'RETIRED'
        return rows
    finally:
        db.close()


def rpc(method, *params):
    response = http.post('http://fisco-node:8545', json={
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': [1, *params]}, timeout=8)
    response.raise_for_status()
    body = response.json()
    assert 'error' not in body, f'FISCO {method} failed: {body.get("error")}'
    return body['result']


def matches(receipt):
    if not receipt or receipt.get('status') not in ('0x0', '0x00', '0x00000000', 0):
        return False
    for log in receipt.get('logs', []):
        topics = log.get('topics', [])
        if log.get('address', '').lower() != CONTRACT or len(topics) != 2 or topics[0].lower() != TOPIC:
            continue
        if int(topics[1], 16) != 37:
            continue
        data = bytes.fromhex(log['data'].removeprefix('0x'))
        def word(index):
            return int.from_bytes(data[index * 32:(index + 1) * 32], 'big')
        def string(index):
            offset = word(index)
            size = int.from_bytes(data[offset:offset + 32], 'big')
            return data[offset + 32:offset + 32 + size].decode('utf-8')
        if (string(0), word(1), string(2), string(3)) == ('KEY_UPDATED', 2, 'A', HASH):
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    before = snapshot()
    height = int(rpc('getBlockNumber'), 16)
    assert height <= 500, 'Chain too large for bounded repair scan; narrow range first'
    found = []
    for number in range(height + 1):
        block = rpc('getBlockByNumber', hex(number), False)
        for tx in block.get('transactions', []):
            tx_hash = tx if isinstance(tx, str) else tx['hash']
            receipt = rpc('getTransactionReceipt', tx_hash)
            if matches(receipt):
                found.append(receipt)
    assert len(found) <= 1, 'Multiple matching events; stop for review'
    if found:
        receipt, action = found[0], 'ALREADY_CONFIRMED'
    elif not args.submit:
        print(json.dumps({'status': 'MISSING', 'scannedThroughBlock': height, 'target': 'A-SSCL-4cfab58e/v2'}))
        return
    else:
        assert os.environ.get('KMS_CHAIN_WRITES_ENABLED') == 'true'
        assert snapshot() == before, 'Target changed during scan'
        from pqkds.kms_service_client import record_chain_event
        tx_hash = record_chain_event('KEY_UPDATED', 37, 2, 'A', HASH)
        assert tx_hash, 'No transaction hash returned; inspect logs/receipts before any retry'
        receipt = rpc('getTransactionReceipt', tx_hash)
        assert matches(receipt), 'Transaction missing the exact expected event'
        action = 'BACKFILLED'
    assert snapshot() == before, 'Key metadata changed during repair'
    print(json.dumps({'status': action, 'keyId': 'A-SSCL-4cfab58e', 'version': 2,
        'chainHash': receipt['transactionHash'], 'blockNumber': receipt['blockNumber'],
        'receiptStatus': receipt['status'], 'eventVerified': True, 'keyMetadataUnchanged': True}))


if __name__ == '__main__':
    main()
