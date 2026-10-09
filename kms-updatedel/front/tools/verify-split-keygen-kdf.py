"""Independent stdlib RFC5869 reference for the frozen WebCrypto HKDF transcript.
Only fixed, public test vectors; never reads real keystores, Django, or databases.
"""
import hashlib
import hmac
import json
import pathlib
import struct
import sys

FIELDS = (
    'schemeId', 'schemeVersion', 'coreFamily', 'variant', 'userId', 'nodeId',
    'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision',
    'keyId', 'keyVersion', 'purpose', 'generationIssuanceId',
)
SALT_TAG = b'KMS-SPLIT-KEYGEN-V1/HKDF-SHA256'
CONTEXT_TAG = b'KMS-SPLIT-KEYGEN-V1/CONTEXT'


def derive(share, secret, context, length):
    info = CONTEXT_TAG
    for field in FIELDS:
        value = context[field].encode('utf-8')
        info += struct.pack('>I', len(value)) + value
    salt = hashlib.sha256(SALT_TAG).digest()
    prk = hmac.new(salt, share + secret, hashlib.sha256).digest()
    previous, output = b'', b''
    for counter in range(1, (length + 31) // 32 + 1):
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        output += previous
    return output[:length]


if __name__ == '__main__':
    if sys.flags.optimize != 0:
        raise RuntimeError('crypto gate refuses optimized Python execution')
    fixture = json.loads((pathlib.Path(__file__).parent / 'fixtures' / 'split-keygen-v1.json').read_text(encoding='utf-8'))
    share = bytes.fromhex(fixture['kgcShareHex'])
    secret = bytes.fromhex(fixture['localSecretHex'])
    if len(share) != 32 or len(secret) != 32 or len(fixture['vectors']) != 2:
        raise ValueError('frozen fixture must contain two 32-byte contributions and exactly two vectors')
    if [vector['seedBytes'] for vector in fixture['vectors']] != [64, 48]:
        raise ValueError('frozen KEM/signature lengths must be 64 and 48 bytes')
    for vector in fixture['vectors']:
        result = derive(share, secret, vector['context'], vector['seedBytes']).hex()
        if '--print' in sys.argv:
            print(vector['context']['schemeId'], result)
        else:
            if len(vector['seedHex']) != vector['seedBytes'] * 2 or result != vector['seedHex']:
                raise ValueError('frozen Python HKDF vector mismatch')
    if '--print' not in sys.argv:
        print('Python stdlib HKDF PASS: 64-byte KEM and 48-byte signature frozen UTF-8/uint32BE vectors')
