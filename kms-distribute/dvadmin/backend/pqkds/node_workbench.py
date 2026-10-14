"""Node dashboard aggregates logical keys, including initialization, without materials."""
import os
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Max, Min
from django.utils import timezone

from . import api_contract as C
from .models import ChainKeyBinding, NodeLongTermKey


def summary(node, now=None):
    now = now or timezone.now()
    today = timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    rows = NodeLongTermKey.objects.filter(node=node)
    # One logical key can have many versions; updates never increase generation count.
    logical = list(rows.order_by().values('algorithm', 'key_id').annotate(
        first_created=Min('create_datetime'), latest_id=Max('id'), versions=Count('id')))
    latest = list(rows.filter(id__in=[item['latest_id'] for item in logical]).values(
        'id', 'algorithm', 'key_id', 'key_version', 'status', 'public_key_hash',
        'expires_at', 'generation_scheme'))
    versions = {item['latest_id']: item['versions'] for item in logical}
    algorithms, states, trend = Counter(), Counter(), Counter()
    for item in logical:
        algorithms[item['algorithm']] += 1
        created = item['first_created']
        if created:
            date = timezone.localtime(created).date() if timezone.is_aware(created) else created.date()
            if date in days:
                trend[date] += 1
    for key in latest:
        state = key['status']
        if key['expires_at'] and key['expires_at'] <= now and state == C.KEY_STATUS_ACTIVE:
            state = C.KEY_STATUS_EXPIRED
        states[state] += 1

    from .chain_backend import is_fabric_did
    bindings = ChainKeyBinding.objects.filter(node=node, long_term_key_id__in=versions)
    fabric = is_fabric_did()
    if fabric:
        from .chain_binding_service import configured_namespace
        bindings = bindings.filter(provider='FABRIC_DID',
            chain_id=os.getenv('FABRIC_DID_CHAIN_ID', '').strip(), namespace=configured_namespace())
    else:
        from .node_fisco_evidence import chain_id, NAMESPACE
        bindings = bindings.filter(provider='FISCO', chain_id=chain_id(), namespace=NAMESPACE)
    evidence = {}
    for binding in bindings.order_by('-sequence').values(
            'long_term_key_id', 'status', 'transaction_valid', 'metadata_matches', 'key_status'):
        evidence.setdefault(binding['long_term_key_id'], binding)
    chain = Counter()
    current = []
    labels = dict(C.KEY_STATUS_CHOICES)
    for key in latest:
        binding = evidence.get(key['id'])
        state = binding['status'] if binding else 'NOT_REGISTERED'
        if state == 'CONFIRMED':
            matches = not fabric or binding['key_status'] == key['status']
            if not (binding['transaction_valid'] and binding['metadata_matches'] and matches):
                state = 'PENDING_VERIFICATION'
        bucket = 'confirmed' if state == 'CONFIRMED' else (
            'failed' if state == 'FAILED' else ('unregistered' if state in (
                'NOT_REGISTERED', 'NOT_CONFIGURED', 'UNSUPPORTED') else 'pending'))
        chain[bucket] += 1
        if key['status'] == C.KEY_STATUS_ACTIVE:
            expired = key['expires_at'] is not None and key['expires_at'] <= now
            current.append(dict(algorithm=key['algorithm'], keyId=key['key_id'],
                keyVersion=key['key_version'], status=C.KEY_STATUS_EXPIRED if expired else key['status'],
                statusLabel=labels[C.KEY_STATUS_EXPIRED if expired else key['status']],
                allowsNewWork=not expired, publicKeyHash=key['public_key_hash'],
                versions=versions[key['id']], generation={'schemeId': key['generation_scheme']}))
    return dict(nodeId=node.node_id, total=len(logical), versionTotal=sum(versions.values()),
        active=states[C.KEY_STATUS_ACTIVE], revoked=states[C.KEY_STATUS_REVOKED],
        algorithms=dict(algorithms), statuses=dict(states), chain=dict(chain), currentKeys=current,
        trend=[dict(date=day.isoformat(), count=trend[day]) for day in days])
