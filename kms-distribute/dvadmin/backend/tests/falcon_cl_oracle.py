"""TEST ONLY vector oracle; never loads Django settings or connects any database.

Uses actual native Falcon TrapGen partial issuance, then creates an ephemeral
TEST_ONLY user matrix for interoperability vectors. Output is test material,
not a production key export. V1 binary matrix material is explicitly adapted to
reference numpy matrices; legacy base64(JSON-array) keys are NOT compatible.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pqkds import falcon_cl_v1 as F
from pqkds.falcon_fast_engine import fast_encrypt, fast_decrypt
from pqkds.falcon_aes_session_encryption import _serialize_ciphertext_fast


def create(path):
    partial = F.issue_partial('TEST_ONLY_FALCON_RECIPIENT')
    p = F.parse_material(partial, 'PARTIAL')
    s = F._short(F.M * F.M).reshape(F.M, F.M)
    public = F.encode_material({**p, 'U_id': p['B'] @ s % F.Q}, 'PUBLIC', p['nodeId'])
    private = F.encode_material({'D_id': p['D_id'], 'S_id': s}, 'PRIVATE', p['nodeId'])
    key = bytes(range(16))
    ct = F.encrypt(public, key)
    assert F.decrypt(private, ct) == key
    pk = F.parse_material(public, 'PUBLIC')
    ref = fast_encrypt(pk['A'], pk['B'], pk['H_id'], pk['U_id'], key, F.N, F.M, F.Q, 1.17)
    assert fast_decrypt(ref['c1'], ref['c2'], ref['c3'], p['D_id'], s, F.Q, 16) == key
    assert F.decrypt(private, _serialize_ciphertext_fast(ref, F.N, F.M, F.Q, 16)) == key
    Path(path).write_text(json.dumps({'testOnly': True, 'partial': partial, 'publicKey': public, 'privateKey': private, 'ciphertext': ct, 'referenceCiphertext': _serialize_ciphertext_fast(ref, F.N, F.M, F.Q, 16), 'keyHex': key.hex()}), encoding='ascii')
    print('PASS actual native Falcon + reference-engine/Python 16-byte exact vectors', file=sys.stderr)


def verify(path):
    result = json.loads(Path(path).read_text(encoding='utf-8'))
    assert result['testOnly'] is True
    for vector in result['vectors']:
        assert F.decrypt(vector['privateKey'], vector['ciphertext']) == bytes.fromhex(vector['keyHex'])
        if 'publicKey' in vector:
            public = F.parse_material(vector['publicKey'], 'PUBLIC')
            private = F.parse_material(vector['privateKey'], 'PRIVATE')
            ct = F.decode_ciphertext(vector['ciphertext'])
            # Independent original reference decrypt, with fresh live matrix buffers.
            assert fast_decrypt(*ct, private['D_id'], private['S_id'], F.Q, 16) == bytes.fromhex(vector['keyHex'])
            assert (public['B'] @ private['S_id'] % F.Q == public['U_id']).all()
    print('PASS browser -> Python/reference decrypt, browser-local S -> U exact relation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['create', 'verify'])
    parser.add_argument('path')
    args = parser.parse_args()
    (create if args.mode == 'create' else verify)(args.path)
