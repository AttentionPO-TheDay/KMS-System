"""Server-managed external SM2/SSCL keys; independent of browser/Demo sessions."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import unicodedata
import uuid
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.db import IntegrityError, transaction
from django.utils import timezone
import requests

from . import node_key_did
from .models import ExternalNodeActivation, Node, NodeKeyDidRecord
from .node_key_registry import register_public_key
from .sm2_crypto import SM2Crypto, SM2_CURVE, SM2_N, _parse_public_point, _point_mul, _point_to_hex


class ActivationError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def configuration():
    if os.getenv('KMS_EXTERNAL_SSCL_ENABLED', 'false').lower() != 'true':
        raise ActivationError('EXTERNAL_SSCL_DISABLED', 503)
    try:
        path = Path(os.environ['KMS_EXTERNAL_SSCL_CONFIG'])
        if path.stat().st_size > 65536:
            raise ValueError()
        config = json.loads(path.read_text(encoding='utf-8'))
        cipher = Fernet(config['encryptionKey'].encode('ascii'))
        clients = config['clients']
        if not isinstance(clients, dict) or not clients:
            raise ValueError()
        for client, digest in clients.items():
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', client) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError()
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        raise ActivationError('EXTERNAL_SSCL_NOT_CONFIGURED', 503) from None
    return clients, cipher


def authenticate(request, clients):
    supplied = request.META.get('HTTP_AUTHORIZATION', '')
    if not supplied.startswith('Bearer ') or not 32 <= len(supplied[7:]) <= 256:
        raise ActivationError('EXTERNAL_AUTH_REQUIRED', 401)
    digest = hashlib.sha256(supplied[7:].encode('utf-8')).hexdigest()
    matches = [client for client, expected in clients.items() if hmac.compare_digest(digest, expected)]
    if len(matches) != 1:
        raise ActivationError('EXTERNAL_AUTH_INVALID', 401)
    return matches[0]


def validate_name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 100 or value != value.strip()
            or any(unicodedata.category(ch).startswith('C') for ch in value)):
        raise ActivationError('INVALID_NODE_NAME', 400)
    return value  # Exact names are identities; do not silently normalize/case-fold.


def validate_algorithm(value):
    if not isinstance(value, str) or value not in ('SM2', 'SSCL'):
        raise ActivationError('INVALID_KEY_ALGORITHM', 400)
    return value


def identity_hash(client, name, algorithm='SM2'):
    # Keep the original SSCL identity hash; SM2 occupies its own namespace.
    identity = [client, name] if algorithm == 'SSCL' else [client, name, algorithm]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def seal(cipher, material):
    return cipher.encrypt(json.dumps(material, separators=(',', ':')).encode()).decode('ascii')


def unseal(cipher, row):
    try:
        material = json.loads(cipher.decrypt(row.encrypted_material.encode('ascii')))
        if material['identity'] != row.node.node_id:
            raise ValueError()
        if not re.fullmatch('[0-9a-f]{64}', material['clientSecret']):
            raise ValueError()
        return material
    except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
        # Never generate a replacement when the original private material is unavailable.
        raise ActivationError('EXTERNAL_PRIVATE_MATERIAL_UNAVAILABLE', 503) from None


def _scalar(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) or int(value, 16) >= SM2_N:
        raise ValueError('Invalid scalar')
    return int(value, 16)


def compose_sscl(client_secret, share):
    """Same SSCL interpolation/composition as front/src/utils/cl-key.js."""
    xs, ys = share['xIndex'], share['yIndex']
    point = share['SSCLKey']
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != 10 or len(ys) != 10:
        raise ValueError('Invalid domain shares')
    if not isinstance(point, str) or not re.fullmatch('04[0-9a-f]{128}', point):
        raise ValueError('Invalid partial key')
    xs = [_scalar(x) for x in xs] + [_scalar(point[2:66])]
    ys = [_scalar(y) for y in ys] + [_scalar(point[66:130])]
    if len(set(xs)) != len(xs):
        raise ValueError('Duplicate share coordinates')
    secret = 0
    for i, x in enumerate(xs):
        top, bottom = 1, 1
        for j, other in enumerate(xs):
            if i != j:
                top = top * (-other) % SM2_N
                bottom = bottom * (x - other) % SM2_N
        secret = (secret + ys[i] * top * pow(bottom, -1, SM2_N)) % SM2_N
    private = (_scalar(client_secret) + secret * xs[-1]) % SM2_N
    if not private:
        raise ValueError('Zero SSCL private scalar')
    px, py = _parse_public_point(share['PPub'], SM2_CURVE)
    result = _point_mul(private, px, py, SM2_CURVE)
    if result is None:
        raise ValueError('Invalid SSCL public point')
    return format(private, '064x'), _point_to_hex(*result)


def issue_partial(identity, ua):
    token = os.getenv('INTERNAL_TOKEN', '')
    if not token:
        raise ActivationError('SSCL_GENERATOR_NOT_CONFIGURED', 503)
    base = os.getenv('GENERATE_JAVA_BASE', 'http://generate-java:9081').rstrip('/')
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(base + '/internal/generate/sscl/partial',
                                    headers={'X-Internal-Token': token},
                                    json={'identity': identity, 'ua': ua},
                                    timeout=(5, 30), allow_redirects=False)
        body = response.json()
        if response.status_code != 200 or body.get('code') != 200:
            raise ValueError()
        data = body['data']
        if data['identity'] != identity or data['ua'] != ua:
            raise ValueError()
        return data
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        raise ActivationError('SSCL_GENERATOR_UNAVAILABLE', 503) from None


def _record(client, name, cipher, algorithm='SM2'):
    digest = identity_hash(client, name, algorithm)
    existing = ExternalNodeActivation.objects.filter(identity_hash=digest).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            # Never adopt another platform's node or an existing browser node by display name.
            node = Node.objects.create(node_id='ext-' + digest[:60], name=name,
                                       initialization_profile='EXTERNAL_' + algorithm,
                                       ip_address='127.0.0.1', port=0, status='PENDING_INIT',
                                       description='外部平台托管' + algorithm + '节点；不作为完整浏览器节点使用')
            # SM2 signing excludes n-1, for which (1+d) has no inverse.
            limit = SM2_N - (2 if algorithm == 'SM2' else 1)
            material = {'identity': node.node_id, 'clientSecret': format(secrets.randbelow(limit) + 1, '064x')}
            return ExternalNodeActivation.objects.create(identity_hash=digest, client_id=client,
                                                         node_name=name, node=node,
                                                         encrypted_material=seal(cipher, material))
    except IntegrityError:
        existing = ExternalNodeActivation.objects.filter(identity_hash=digest).first()
        if existing:
            return existing
        raise ActivationError('EXTERNAL_NODE_IDENTITY_CONFLICT') from None


def _algorithm(row):
    algorithm = {'EXTERNAL_SSCL': 'SSCL', 'EXTERNAL_SM2': 'SM2'}.get(row.node.initialization_profile)
    if not algorithm or (row.key_id and row.key.algorithm != algorithm):
        raise ActivationError('EXTERNAL_NODE_PROFILE_MISMATCH')
    return algorithm


def _check_node(row):
    _algorithm(row)
    if row.node.status.upper() not in {'ACTIVE', 'PENDING_INIT'}:
        raise ActivationError('EXTERNAL_NODE_DISABLED')


def activate(client, name, cipher, *, algorithm='SM2', generator=None, did_factory=None):
    algorithm = validate_algorithm(algorithm)
    # Check before creating anything. Do not turn on chain writes or bypass existing DID gates.
    if not node_key_did.enabled() or not os.getenv('INTERNAL_TOKEN', '').strip():
        raise ActivationError('EXTERNAL_DID_NOT_CONFIGURED', 503)
    row = _record(client, validate_name(name), cipher, algorithm)
    token = str(uuid.uuid4())
    with transaction.atomic():
        row = ExternalNodeActivation.objects.select_for_update().select_related('node', 'key').get(pk=row.pk)
        _check_node(row)
        if row.key_id:
            if row.key.status != 'ACTIVE' or not row.key.allows_new_work:
                raise ActivationError('EXTERNAL_PUBLIC_KEY_INACTIVE')
            material = unseal(cipher, row)
            if material.get('publicKey') != row.key.public_key or not material.get('privateKey'):
                raise ActivationError('EXTERNAL_PRIVATE_MATERIAL_UNAVAILABLE', 503)
            token = ''
        elif row.lease_expires_at and row.lease_expires_at > timezone.now():
            return result(row), 202
        else:
            row.lease_token = token
            row.lease_expires_at = timezone.now() + timedelta(minutes=2)
            row.save(update_fields=['lease_token', 'lease_expires_at', 'updated_at'])
            material = unseal(cipher, row)
    if token:
        try:
            if algorithm == 'SM2':
                private = material['clientSecret']
                public = SM2Crypto.public_key_of(private)
                material.update(privateKey=private, publicKey=public, algorithm='SM2', curve='sm2p256v1')
            else:
                ua = SM2Crypto.public_key_of(material['clientSecret'])
                share = (generator or issue_partial)(row.node.node_id, ua)
                if not isinstance(share, dict) or share.get('identity') != row.node.node_id or share.get('ua') != ua:
                    raise ActivationError('INVALID_SSCL_GENERATOR_RESPONSE', 502)
                try:
                    private, public = compose_sscl(material['clientSecret'], share)
                except (KeyError, ValueError, TypeError, OverflowError):
                    raise ActivationError('INVALID_SSCL_GENERATOR_RESPONSE', 502) from None
                material.update(privateKey=private, publicKey=public, domainPublicKey=share['PPub'])
            with transaction.atomic():
                row = ExternalNodeActivation.objects.select_for_update().select_related('node').get(pk=row.pk)
                # Lease expiry alone cannot permit a late result to overwrite a newer owner.
                if row.lease_token != token or not row.lease_expires_at or row.lease_expires_at <= timezone.now():
                    raise ActivationError('EXTERNAL_ACTIVATION_LEASE_EXPIRED')
                row.node = Node.objects.select_for_update().get(pk=row.node_id)
                _check_node(row)
                key = register_public_key(row.node, algorithm=algorithm, public_key=public,
                                          key_id=algorithm.lower() + '-' + row.identity_hash[:59], key_version=1)
                row.key = key
                row.encrypted_material = seal(cipher, material)
                row.lease_token, row.lease_expires_at = '', None
                row.save(update_fields=['key', 'encrypted_material', 'lease_token', 'lease_expires_at', 'updated_at'])
                # External profiles initialize one algorithm; full nodes retain all-algorithm checks.
                row.node.status, row.node.initialized_at = 'active', timezone.now()
                row.node.save(update_fields=['status', 'initialized_at'])
        finally:
            ExternalNodeActivation.objects.filter(pk=row.pk, lease_token=token).update(lease_token='', lease_expires_at=None)
    # Network/ledger calls occur after durable key registration, outside the DB transaction.
    evidence = node_key_did.register(row.key, client_factory=did_factory)
    row.refresh_from_db()
    body = result(row, evidence)
    state = (evidence or {}).get('status')
    return body, 200 if body['didConfirmed'] else 502 if state == 'FAILED' else 503 if state == 'DISABLED' else 202


def result(row, evidence=None):
    node, key = row.node, row.key
    evidence = evidence if evidence is not None else _saved_evidence(key)
    confirmed = bool(evidence and evidence.get('status') == 'CONFIRMED'
                     and evidence.get('transactionValid') is True and evidence.get('metadataMatches') is True)
    return {'nodeName': row.node_name, 'nodeId': node.node_id, 'nodeStatus': node.status.upper(),
            'initializationProfile': node.initialization_profile, 'algorithm': _algorithm(row),
            'curve': 'sm2p256v1',
            'publicKeyRegistrationStatus': 'REGISTERED' if key else 'PENDING',
            'publicKeyStatus': key.status if key else 'PENDING',
            'publicKey': key.public_key if key else '', 'keyId': key.key_id if key else '',
            'keyVersion': key.key_version if key else None,
            'sysPid': (evidence or {}).get('sysPid', ''), 'didConfirmed': confirmed, 'didOnchain': evidence}


def _saved_evidence(key):
    record = NodeKeyDidRecord.objects.filter(key=key).first() if key else None
    return node_key_did.payload(record) if record else None


def _query_record(client, name=None, *, sys_pid=None, algorithm=None):
    if (name is None) == (sys_pid is None):
        raise ActivationError('INVALID_ACTIVATION_REQUEST', 400)
    rows = ExternalNodeActivation.objects.select_related('node', 'key')
    if sys_pid is not None:
        if not isinstance(sys_pid, str) or not re.fullmatch('[0-9a-f]{182}', sys_pid):
            raise ActivationError('INVALID_SYS_PID', 400)
        row = rows.filter(client_id=client, key__did_record__sys_pid=sys_pid).first()
    else:
        algorithm = validate_algorithm('SM2' if algorithm is None else algorithm)
        row = rows.filter(identity_hash=identity_hash(client, validate_name(name), algorithm)).first()
    # Compare exactly as well: MySQL's client_id collation may ignore case.
    if not row or row.client_id != client:
        raise ActivationError('EXTERNAL_NODE_NOT_FOUND', 404)
    actual = _algorithm(row)
    if algorithm is not None and actual != validate_algorithm(algorithm):
        raise ActivationError('EXTERNAL_KEY_ALGORITHM_MISMATCH')
    return row


def private_key(client, cipher, *, name=None, sys_pid=None, algorithm=None):
    """Explicit, platform-scoped export of the original encrypted key material."""
    row = _query_record(client, name, sys_pid=sys_pid, algorithm=algorithm)
    _check_node(row)
    if not row.key_id:
        raise ActivationError('EXTERNAL_PRIVATE_KEY_NOT_READY')
    if row.key.status != 'ACTIVE' or not row.key.allows_new_work:
        raise ActivationError('EXTERNAL_PUBLIC_KEY_INACTIVE')
    material = unseal(cipher, row)
    try:
        private = material['privateKey']
        scalar = _scalar(private)
        if not scalar or material['publicKey'] != row.key.public_key:
            raise ValueError()
        if _algorithm(row) == 'SM2':
            if scalar >= SM2_N - 1 or SM2Crypto.public_key_of(private) != row.key.public_key:
                raise ValueError()
            exported = {'privateKey': private, 'curve': 'sm2p256v1'}
        else:
            domain = material['domainPublicKey']
            point = _parse_public_point(domain, SM2_CURVE)
            public = _point_mul(scalar, *point, SM2_CURVE)
            if public is None or _point_to_hex(*public) != row.key.public_key:
                raise ValueError()
            exported = {'privateKey': private, 'domainPublicKey': domain}
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ActivationError('EXTERNAL_PRIVATE_MATERIAL_UNAVAILABLE', 503) from None
    return exported


def query(client, name=None, *, sys_pid=None, algorithm=None, did_factory=None):
    row = _query_record(client, name, sys_pid=sys_pid, algorithm=algorithm)
    evidence = _saved_evidence(row.key)
    if evidence and evidence.get('sysPid') and evidence.get('status') != 'CONFIRMED':
        evidence = node_key_did.process(row.key.did_record, client_factory=did_factory)
    return result(row, evidence)
