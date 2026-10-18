"""Contributory group key establishment over existing authenticated pairwise sessions.

The coordinator routes ciphertext and serializes rounds. It does not run MPC or
derive a group key. Security assumes honest participants and uncompromised clients
and pairwise channels; no forward-secrecy or malicious-party proof is claimed.
"""
import base64
import hashlib
import hmac
import itertools
import json
import re
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import GroupKeyAgreement, GroupAgreementMember, Node, SessionKey, UserNodeAuthorization

PROTOCOL = 'kms-contributory-v1'
TERMINAL = {'failed', 'expired', 'closed'}
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class AgreementError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def scope(group):
    return [PROTOCOL, group.agreement_id, [row['nodeId'] for row in group.roster],
            group.channels, group.expires_at.isoformat()]


def actor(identity):
    if identity.get('principalType') == 'ADMIN' or not identity.get('userId'):
        raise AgreementError('仅节点账号可以参与多方协商', 403)
    node = Node.objects.filter(sys_user_id=identity['userId']).first()
    if node is None or node.status != 'active':
        raise AgreementError('当前账号没有活跃节点', 403)
    return node


def validate_channel_keys(channel):
    from . import api_contract as C
    from .node_key_registry import require_key_version
    if not channel.recipient_key_id or not channel.falcon_key_id:
        raise AgreementError('基础会话缺少密钥版本记录，请重新建立会话')
    try:
        algorithm = C.canonical_algorithm(channel.session_type)
        if algorithm not in C.PROTECTION_ALGORITHMS:
            raise AgreementError('历史基础会话保护算法不受支持，请重新建立会话')
        recipient_key = require_key_version(channel.node2, algorithm, channel.recipient_key_id,
                                            channel.recipient_key_version, for_new_work=False)
        signing_key = require_key_version(channel.node1, 'FALCON', channel.falcon_key_id,
                                         channel.falcon_key_version, for_new_work=False)
        if any(key.status not in (C.KEY_STATUS_ACTIVE, C.KEY_STATUS_RETIRED) for key in (recipient_key, signing_key)):
            raise AgreementError('基础会话引用的长期密钥尚未生效')
    except C.ContractError as exc:
        raise AgreementError('基础会话密钥已不可用，请重新建立会话') from exc


def valid_channel(channel, now):
    if channel.status not in ('established', 'blockchain_recorded') or channel.expires_at <= now:
        raise AgreementError('参与节点间的基础会话尚未建立、已关闭或已过期')
    if channel.node1.status != 'active' or channel.node2.status != 'active':
        raise AgreementError('参与节点已停用')
    if not UserNodeAuthorization.objects.filter(user_id=channel.node1.sys_user_id,
                                                node_id=channel.node2_id, status='active').exists():
        raise AgreementError('基础会话的通信授权已失效')
    validate_channel_keys(channel)


def event(group, stage, node_id=''):
    group.events = [*group.events, {'stage': stage, 'nodeId': node_id, 'at': timezone.now().isoformat()}]


def refresh(group):
    """Lazy expiry/invalidation also applies to established agreements."""
    if group.status in TERMINAL:
        return
    reason = ''
    now = timezone.now()
    if group.expires_at <= now:
        group.status, reason = 'expired', '协商或密钥有效期已结束'
    elif group.initiator_id is None or group.members.filter(node__isnull=True).exists():
        group.status, reason = 'failed', '参与节点已被删除'
    elif not all(UserNodeAuthorization.objects.filter(user_id=group.initiator.sys_user_id,
                 node__node_id=row['nodeId'], status='active').exists()
                 for row in group.roster if row['nodeId'] != group.initiator_node_code):
        group.status, reason = 'failed', '发起方的通信授权已失效'
    else:
        for left, right, sid in group.channels:
            channel = SessionKey.objects.select_related('node1', 'node2').filter(session_id=sid).first()
            try:
                if channel is None or {channel.node1.node_id, channel.node2.node_id} != {left, right}:
                    raise AgreementError('基础会话不存在或归属不匹配')
                valid_channel(channel, now)
            except AgreementError as exc:
                group.status, reason = 'failed', str(exc)
                break
    if reason:
        group.failure_reason = reason
        event(group, group.status)
        group.save(update_fields=['status', 'failure_reason', 'events'])


def project(group, node, detail=False):
    members = {member.participant_node_code: member for member in group.members.all()}
    data = {
        'agreementId': group.agreement_id, 'protocol': PROTOCOL, 'selfNodeId': node.node_id,
        'initiatorNodeId': group.initiator_node_code, 'status': group.status,
        'scopeHash': group.scope_hash, 'transcriptHash': group.transcript_hash,
        'createdAt': group.created_at.isoformat(), 'expiresAt': group.expires_at.isoformat(),
        'failureReason': group.failure_reason, 'channels': group.channels,
        'members': [{'nodeId': row['nodeId'], 'name': row['name'],
                     'commitment': members[row['nodeId']].commitment,
                     'committedAt': _iso(members[row['nodeId']].committed_at),
                     'exchangedAt': _iso(members[row['nodeId']].exchanged_at),
                     'confirmedAt': _iso(members[row['nodeId']].confirmed_at)} for row in group.roster],
        'committedCount': sum(bool(m.commitment) for m in members.values()),
        'exchangedCount': sum(bool(m.exchanged_at) for m in members.values()),
        'confirmedCount': sum(bool(m.confirmed_at) for m in members.values()),
    }
    if detail:
        data['events'] = group.events
        # No proof is returned, even to its submitter. Never expose others' packets.
        data['inbox'] = [{'fromNodeId': sender, **packet} for sender, member in members.items()
                         for packet in member.packets if packet['toNodeId'] == node.node_id] if group.status not in TERMINAL else []
    return data


def _iso(value):
    return value.isoformat() if value else None


@transaction.atomic
def create(node, payload):
    # Serialize the per-initiator quota; independent groups lock different rows.
    node = Node.objects.select_for_update().filter(pk=node.pk, status='active').first()
    if node is None:
        raise AgreementError('发起节点已停用或删除', 403)
    requested = payload.get('participantNodeIds')
    if (not isinstance(requested, list) or not 2 <= len(requested) <= 7 or
            any(not isinstance(item, str) or not item for item in requested) or
            len(set(requested)) != len(requested) or node.node_id in requested):
        raise AgreementError('请选择2至7个不同的对端节点，含本节点共3至8个参与者')
    nodes = list(Node.objects.filter(node_id__in=[node.node_id, *requested]).order_by('node_id'))
    if len(nodes) != len(requested) + 1 or any(n.status != 'active' for n in nodes):
        raise AgreementError('参与节点不存在或未处于活跃状态')
    allowed = set(UserNodeAuthorization.objects.filter(user_id=node.sys_user_id, status='active').values_list('node_id', flat=True))
    if any(n.pk not in allowed for n in nodes if n.pk != node.pk):
        raise AgreementError('发起方尚未获得与所有参与节点通信的授权', 403)
    now, channels, expiries = timezone.now(), [], []
    if GroupKeyAgreement.objects.filter(initiator=node, status__in=('committing', 'exchanging', 'confirming'),
                                        expires_at__gt=now).count() >= 10:
        raise AgreementError('未完成的协商过多，请先处理或关闭现有协商', 409)
    for left, right in itertools.combinations(nodes, 2):
        candidates = SessionKey.objects.filter(
            Q(node1=left, node2=right) | Q(node1=right, node2=left),
            status__in=('established', 'blockchain_recorded'), expires_at__gt=now,
        ).select_related('node1', 'node2').order_by('-expires_at', '-id')[:20]
        selected = None
        for channel in candidates:
            try:
                valid_channel(channel, now)
                selected = channel
                break
            except AgreementError:
                continue
        if selected is None:
            raise AgreementError(f'{left.name}与{right.name}之间缺少有效且已确认的基础会话')
        channels.append([left.node_id, right.node_id, selected.session_id])
        expiries.append(selected.expires_at)
    group = GroupKeyAgreement(
        agreement_id=f'gka-{uuid.uuid4()}', initiator=node, initiator_node_code=node.node_id,
        roster=[{'nodeId': n.node_id, 'name': n.name} for n in nodes], channels=channels,
        expires_at=min(now + timedelta(minutes=30), *expiries),
    )
    group.scope_hash = digest(scope(group))
    event(group, 'created', node.node_id)
    group.save()
    GroupAgreementMember.objects.bulk_create([GroupAgreementMember(agreement=group, node=n, participant_node_code=n.node_id) for n in nodes])
    return project(group, node, True)


def _locked(group_id, node):
    group = GroupKeyAgreement.objects.select_for_update().filter(agreement_id=group_id, members__node=node).first()
    if group is None:
        raise AgreementError('协商不存在或你不是参与者', 404)
    refresh(group)
    return group


@transaction.atomic
def detail(group_id, node, include_packets=True):
    return project(_locked(group_id, node), node, include_packets)


def listing(node):
    ids = list(GroupKeyAgreement.objects.filter(members__node=node).values_list('agreement_id', flat=True)[:100])
    return [detail(group_id, node, False) for group_id in ids]


def peers(node):
    allowed = UserNodeAuthorization.objects.filter(user_id=node.sys_user_id, status='active').values_list('node_id', flat=True)
    return [{'nodeId': n.node_id, 'name': n.name} for n in Node.objects.filter(
        pk__in=allowed, status='active').exclude(pk=node.pk).order_by('node_id')]


def _hex(value):
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise AgreementError('摘要或确认值必须为64位小写十六进制')
    return value


def _packet_bytes(value, length):
    if not isinstance(value, str) or len(value) > 128:
        raise AgreementError('贡献密文编码不合法')
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise AgreementError('贡献密文编码不合法') from exc
    if len(raw) != length or base64.b64encode(raw).decode('ascii') != value:
        raise AgreementError('贡献密文长度或编码不合法')
    return value


@transaction.atomic
def operate(group_id, node, action, payload):
    group = _locked(group_id, node)
    if group.status in TERMINAL:
        return project(group, node, True)
    member = group.members.get(node=node)
    if action == 'close':
        group.status, group.failure_reason = 'closed', '参与者终止协商或关闭密钥'
        event(group, 'closed', node.node_id)
        group.save(update_fields=['status', 'failure_reason', 'events'])
        return project(group, node, True)
    if action == 'commit':
        commitment = _hex(payload.get('commitment'))
        if member.commitment:
            if not hmac.compare_digest(member.commitment, commitment):
                raise AgreementError('已提交的随机贡献承诺不可替换', 409)
            return project(group, node, True)
        if group.status != 'committing':
            raise AgreementError('当前阶段不接受贡献承诺', 409)
        member.commitment, member.committed_at = commitment, timezone.now()
        member.save(update_fields=['commitment', 'committed_at'])
        event(group, 'committed', node.node_id)
        if not group.members.filter(commitment='').exists():
            commitments = {m.participant_node_code: m.commitment for m in group.members.all()}
            group.transcript_hash = digest([group.scope_hash, [[row['nodeId'], commitments[row['nodeId']]] for row in group.roster]])
            group.status = 'exchanging'
            event(group, 'exchanging')
    elif action == 'exchange':
        packets = payload.get('packets')
        targets = [row['nodeId'] for row in group.roster if row['nodeId'] != node.node_id]
        if not isinstance(packets, list) or len(packets) != len(targets):
            raise AgreementError('必须向每一个其他参与者发送一份贡献密文')
        normalized = {}
        for packet in packets:
            if not isinstance(packet, dict) or set(packet) != {'toNodeId', 'channelSessionId', 'iv', 'ciphertext'}:
                raise AgreementError('贡献包包含非法字段')
            target = packet['toNodeId']
            if not isinstance(target, str) or target not in targets or target in normalized:
                raise AgreementError('贡献包接收方重复或不属于本次协商')
            expected = next(sid for a, b, sid in group.channels if {a, b} == {node.node_id, target})
            if packet['channelSessionId'] != expected:
                raise AgreementError('贡献包使用了错误的基础会话')
            _packet_bytes(packet['iv'], 12)
            _packet_bytes(packet['ciphertext'], 48)
            normalized[target] = packet
        packets = [normalized[target] for target in targets]
        if member.exchanged_at:
            if member.packets != packets:
                raise AgreementError('已提交的贡献密文不可替换', 409)
            return project(group, node, True)
        if group.status != 'exchanging':
            raise AgreementError('需全员承诺完成后才能交换贡献', 409)
        member.packets, member.exchanged_at = packets, timezone.now()
        member.save(update_fields=['packets', 'exchanged_at'])
        event(group, 'exchanged', node.node_id)
        if not group.members.filter(exchanged_at__isnull=True).exists():
            group.status = 'confirming'
            event(group, 'confirming')
    elif action == 'confirm':
        proof = _hex(payload.get('proof'))
        if payload.get('transcriptHash') != group.transcript_hash:
            raise AgreementError('协商记录摘要不一致', 409)
        if member.confirmed_at:
            if not hmac.compare_digest(member.proof, proof):
                raise AgreementError('已提交的密钥确认不可替换', 409)
            return project(group, node, True)
        if group.status != 'confirming':
            raise AgreementError('需全员贡献交换完成后才能确认密钥', 409)
        member.proof, member.confirmed_at = proof, timezone.now()
        member.save(update_fields=['proof', 'confirmed_at'])
        event(group, 'confirmed', node.node_id)
        if not group.members.filter(confirmed_at__isnull=True).exists():
            proofs = list(group.members.values_list('proof', flat=True))
            if all(hmac.compare_digest(proofs[0], item) for item in proofs[1:]):
                group.status = 'established'
            else:
                group.status, group.failure_reason = 'failed', '全员密钥确认证明不一致'
            event(group, group.status)
    else:
        raise AgreementError('不支持的协商操作')
    group.save(update_fields=['status', 'transcript_hash', 'failure_reason', 'events'])
    return project(group, node, True)
