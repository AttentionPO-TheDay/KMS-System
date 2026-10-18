"""Read only: exact affected public metadata, no production Django startup."""
import json
import os
import pymysql
import requests

db = pymysql.connect(host=os.getenv('DATABASE_HOST', 'mysql'),
                     port=int(os.getenv('DATABASE_PORT', '3306')),
                     user=os.getenv('DATABASE_USER', 'root'),
                     password=os.getenv('DATABASE_PASSWORD', ''),
                     database=os.getenv('DATABASE_NAME', 'falcon_kds'),
                     cursorclass=pymysql.cursors.DictCursor)
try:
    with db.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        cursor.execute('''SELECT k.id,k.node_id,n.node_id AS node_code,k.algorithm,k.key_id,
            k.key_version,k.status,k.public_key_hash,k.effective_at
            FROM dvadmin_pqkds_node_long_term_keys k
            JOIN dvadmin_pqkds_nodes n ON n.id=k.node_id
            WHERE k.key_id=%s ORDER BY k.key_version''', ('A-SSCL-4cfab58e',))
        rows = cursor.fetchall()
    db.rollback()
finally:
    db.close()
print(json.dumps({'targetVersions': rows}, default=str))
r = requests.post('http://fisco-node:8545', json={
    'jsonrpc': '2.0', 'id': 1, 'method': 'getBlockNumber', 'params': [1]}, timeout=8)
r.raise_for_status()
body = r.json()
assert 'error' not in body, 'FISCO RPC rejected block query'
print(json.dumps({'fiscoBlockNumber': body.get('result')}))
