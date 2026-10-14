"""Persist schedules and serialize browser rotation across devices/tabs.

Only registry state can establish success, never a client success flag.
"""
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from .models import Node, NodeLongTermKey, NodeKeyAutoUpdate

ALGORITHMS = {'SM2', 'SSCL', 'KYBER', 'FALCON', 'FALCON_CL_V1'}


def payload(row):
    def iso(value):
        return value.isoformat() if value else None
    return {
        'algorithm': row.algorithm, 'keyId': row.key_id, 'enabled': row.enabled,
        'intervalMinutes': row.interval_minutes, 'nextRunAt': iso(row.next_run_at),
        'lastRunAt': iso(row.last_run_at), 'lastResult': row.last_result,
        'lastMessage': row.last_message, 'running': bool(
            row.lease_token and row.lease_until and row.lease_until > timezone.now()),
    }


def current_key(node, algorithm):
    return NodeLongTermKey.objects.filter(
        node=node, algorithm=algorithm, status='ACTIVE').first()


def finish(row, key, now, message=''):
    success = bool(key and key.key_id == row.key_id and key.key_version > row.from_version)
    row.last_run_at = now
    row.last_result = 'SUCCESS' if success else 'FAILED'
    row.last_message = ('已登记生产版本 v%s' % key.key_version) if success else (message or '执行未完成，请检查本机材料')[:500]
    row.next_run_at = now + timedelta(minutes=row.interval_minutes) if success else now + timedelta(minutes=1)
    row.lease_token = ''
    row.lease_until = None
    row.save()
    return payload(row)


@transaction.atomic
def configure(node, data):
    node = Node.objects.select_for_update().get(pk=node.pk)
    algorithm = data.get('algorithm')
    if algorithm not in ALGORITHMS or set(data) != {'algorithm', 'keyId', 'enabled', 'intervalMinutes'}:
        raise ValueError('仅接受 algorithm、keyId、enabled、intervalMinutes')
    if type(data['enabled']) is not bool or type(data['intervalMinutes']) is not int or not 1 <= data['intervalMinutes'] <= 525600:
        raise ValueError('更新间隔必须是 1 至 525600 分钟的整数，enabled 必须是布尔值')
    key = current_key(node, algorithm)
    row = NodeKeyAutoUpdate.objects.filter(node=node, algorithm=algorithm).first()
    if not isinstance(data['keyId'], str) or not data['keyId'] or (not data['enabled'] and row and data['keyId'] != row.key_id):
        raise ValueError('配置的 keyId 与原密钥不一致')
    if data['enabled'] and (node.status == 'disabled' or not key or key.key_id != data['keyId']):
        raise ValueError('只能为本节点当前在用的密钥开启自动更新')
    if not row and (not key or key.key_id != data['keyId']):
        raise ValueError('未找到本节点的生产密钥')
    if row and row.lease_token and row.lease_until and row.lease_until > timezone.now() and data['enabled']:
        raise ValueError('该密钥正在更新，请完成后再调整间隔')
    row = row or NodeKeyAutoUpdate(node=node, algorithm=algorithm)
    if row.key_id != data['keyId']:
        row.last_run_at = None
        row.last_result = ''
        row.last_message = ''
        row.lease_token = ''
        row.lease_until = None
    row.key_id = data['keyId']
    row.enabled = data['enabled']
    row.interval_minutes = data['intervalMinutes']
    row.next_run_at = timezone.now() + timedelta(minutes=row.interval_minutes) if row.enabled else None
    row.save()
    return payload(row)


@transaction.atomic
def claim(node, algorithm):
    node = Node.objects.select_for_update().get(pk=node.pk)
    row = NodeKeyAutoUpdate.objects.filter(node=node, algorithm=algorithm).first()
    now = timezone.now()
    if not row or not row.enabled or node.status == 'disabled':
        return None
    key = current_key(node, algorithm)
    if not key or key.key_id != row.key_id:
        row.enabled = False
        row.last_result = 'STOPPED'
        row.last_run_at = now
        row.last_message = '原密钥已回收或替换，自动更新已停止，请为当前密钥重新配置'
        row.next_run_at = None
        row.lease_token = ''
        row.lease_until = None
        row.save()
        return None
    if row.lease_token:
        # Recover a lost completion/registration response without generating again.
        if row.lease_until and row.lease_until > now:
            return None
        if key.key_version > row.from_version:
            finish(row, key, now)
            return None
    if not row.next_run_at or row.next_run_at > now:
        return None
    row.lease_token = str(uuid4())
    row.lease_until = now + timedelta(minutes=10)
    row.from_version = key.key_version
    row.save()
    return {**payload(row), 'leaseToken': row.lease_token, 'fromVersion': row.from_version}


@transaction.atomic
def complete(node, data):
    node = Node.objects.select_for_update().get(pk=node.pk)
    row = NodeKeyAutoUpdate.objects.filter(node=node, algorithm=data.get('algorithm')).first()
    if not row or not row.lease_token or row.lease_token != data.get('leaseToken'):
        raise ValueError('自动更新执行锁已失效')
    result = finish(row, current_key(node, row.algorithm), timezone.now(), str(data.get('message') or ''))
    if not row.enabled:
        row.next_run_at = None
        row.save(update_fields=['next_run_at'])
        result = payload(row)
    return result


@transaction.atomic
def registered(node, algorithm, key_id, version):
    """Manual rotation also restarts the interval; active leases complete separately."""
    Node.objects.select_for_update().get(pk=node.pk)
    row = NodeKeyAutoUpdate.objects.filter(node=node, algorithm=algorithm, key_id=key_id).first()
    if row and row.enabled and not row.lease_token:
        row.next_run_at = timezone.now() + timedelta(minutes=row.interval_minutes)
        row.save(update_fields=['next_run_at'])
