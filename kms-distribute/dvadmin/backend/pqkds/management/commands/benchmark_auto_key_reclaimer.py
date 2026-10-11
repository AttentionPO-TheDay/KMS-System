"""Isolated MySQL acceptance benchmark. Never run against a business database."""
import os
import time
import hashlib
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pqkds.auto_revoke_service import run_once
from pqkds.chain_backend import is_fabric_did
from pqkds.models import (ChainKeyBinding, Node, NodeKeyInspection, NodeLongTermKey,
                          PreDistributedKey, SessionKey, SessionKeyInvalidation)


class Command(BaseCommand):
    help = 'Verify 5,000 end-to-end automatic revocations in an isolated bench database.'

    def handle(self, *args, **options):
        database_name = os.environ.get('DATABASE_NAME', '')
        if not database_name.startswith('kms_auto_revoke_bench_'):
            raise CommandError('拒绝在非专用压测数据库创建或回收密钥')
        if Node.objects.exists():
            raise CommandError('专用压测数据库非空；请创建新的空库再测试')

        count = 5000
        now = timezone.now()
        material = '04' + '1' * 128
        nodes = [Node(node_id=f'bench-node-{i:05d}', name=f'Bench {i}',
                      ip_address='127.0.0.1', port=10000 + i,
                      gm_public_key=material) for i in range(count)]
        Node.objects.bulk_create(nodes, batch_size=1000)
        nodes = list(Node.objects.order_by('id').only('id', 'node_id'))

        keys = [NodeLongTermKey(node_id=n.pk, algorithm='SM2', key_id=f'bench-key-{i:05d}',
                                key_version=1, status='ACTIVE', active_slot='SM2',
                                public_key='' if i % 3 == 0 else material,
                                public_key_hash='' if i % 3 == 1 else '0' * 64)
                for i, n in enumerate(nodes)]
        NodeLongTermKey.objects.bulk_create(keys, batch_size=1000)
        warning_node = Node.objects.create(node_id='bench-warning', name='Bench warning',
                                           ip_address='127.0.0.1', port=16000,
                                           gm_public_key='different-public-material')
        NodeLongTermKey.objects.create(
            node=warning_node, algorithm='SM2', key_id='bench-warning-key',
            key_version=1, status='ACTIVE', public_key=material,
            public_key_hash=hashlib.sha256(material.encode()).hexdigest())

        pools = [PreDistributedKey(pool_id=f'bench-pool-{i:05d}', key_index=0,
                                   node1_id=n.pk, node2_id=None, algorithm='kyber_kem',
                                   wrapping_algorithm='gm_sm2',
                                   long_term_key_id=f'bench-key-{i:05d}',
                                   long_term_key_version=1,
                                   encrypted_key_data='{}', key_hash='0' * 64,
                                   expires_at=now + timedelta(days=1), status='READY')
                 for i, n in enumerate(nodes)]
        PreDistributedKey.objects.bulk_create(pools, batch_size=1000)

        sessions = [SessionKey(session_id=f'bench-session-{i:05d}', node1_id=n.pk,
                               node2_id=n.pk, encrypted_session_key='x',
                               key_exchange_data='{}', session_type='gm_sm2',
                               recipient_key_id=f'bench-key-{i:05d}',
                               recipient_key_version=1,
                               expires_at=now + timedelta(days=1), status='established')
                    for i, n in enumerate(nodes)]
        SessionKey.objects.bulk_create(sessions, batch_size=1000)

        t0 = time.perf_counter()
        result = run_once()
        elapsed = time.perf_counter() - t0
        rate = count / elapsed
        checks = {
            'revoked_keys': NodeLongTermKey.objects.filter(status='REVOKED').count(),
            'revoked_pool_items': PreDistributedKey.objects.filter(status='REVOKED').count(),
            'revoked_sessions': SessionKey.objects.filter(status='revoked').count(),
            'session_records': SessionKeyInvalidation.objects.filter(reason='automatic_revocation').count(),
            'key_audit_records': NodeKeyInspection.objects.filter(action='AUTO_REVOKED').count(),
            'cleared_node_public_keys': Node.objects.filter(gm_public_key='').count(),
        }
        if is_fabric_did():
            checks['fabric_revoke_bindings'] = ChainKeyBinding.objects.filter(
                event_type='REVOKED', key_status='REVOKED').count()
        again = run_once()
        warning = NodeKeyInspection.objects.filter(
            key__key_id='bench-warning-key', action='PENDING_REVIEW',
            severity='WARNING').exists()
        warning_key_active = NodeLongTermKey.objects.filter(
            key_id='bench-warning-key', status='ACTIVE').exists()
        self.stdout.write(f'elapsed_seconds={elapsed:.4f} keys_per_second={rate:.1f}')
        self.stdout.write(f'first={result} second={again} checks={checks} '
                          f'warning={warning} warning_key_active={warning_key_active}')
        if (any(value != count for value in checks.values()) or result['keys'] != count
                or again['keys'] != 0 or not warning or not warning_key_active):
            raise CommandError('完整性或幂等性检查失败')
        if rate < 5000:
            raise CommandError(f'吞吐未达标：{rate:.1f} 条/秒 < 5000 条/秒')
