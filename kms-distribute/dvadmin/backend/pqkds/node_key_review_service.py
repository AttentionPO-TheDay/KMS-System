"""Administrator dispositions. Lock Node before key/inspection, like rotations."""
from django.db.models import Q
from django.utils import timezone

from . import api_contract as C
from .auto_revoke_service import inspect_key
from .key_pool_service import KeyPoolService
from .key_revocation_service import revoke_long_term_key
from .models import PreDistributedKey, SessionKey
from .session_invalidation_service import SessionInvalidationService


def inspection_payload(inspection):
    return {
        'rule': inspection.rule, 'severity': inspection.severity,
        'action': inspection.action, 'batchId': inspection.batch_id,
        'detectedAt': inspection.detected_at.isoformat(),
        'actionAt': inspection.action_at.isoformat() if inspection.action_at else None,
        'handledBy': inspection.handled_by,
        'handledAt': inspection.handled_at.isoformat() if inspection.handled_at else None,
        'disposition': inspection.disposition, 'dispositionNote': inspection.disposition_note,
    }


def key_impact(key, node):
    """Read-only; exactly the precise + historical scope of revoke_long_term_key."""
    family = C.wrapping_algorithms_for(key.algorithm)
    scope = PreDistributedKey.objects.filter(
        Q(node1=node) | Q(node2=node),
        status__in=KeyPoolService.POOL_STATUS_READY_VALUES + (KeyPoolService.POOL_STATUS_RESERVED,),
    )
    precise = scope.filter(long_term_key_id=key.key_id, long_term_key_version=key.key_version)
    historical = scope.filter(long_term_key_id__isnull=True).filter(
        Q(wrapping_algorithm__in=family) | Q(algorithm__in=family))
    sessions = SessionKey.objects.filter(
        Q(node1=node) | Q(node2=node),
        status__in=['initiated', 'established', 'blockchain_recorded'])
    affected = []
    for session in sessions:
        matches, why = SessionInvalidationService._session_references(
            session, node, key.algorithm, key.key_id, key.key_version, family)
        if matches:
            affected.append({'sessionId': session.session_id, 'status': session.status,
                             'match': why})
    return {'poolItems': precise.count() + historical.count(),
            'precisePoolItems': precise.count(), 'historicalPoolItems': historical.count(),
            'sessions': len(affected), 'sessionItems': affected,
            'historicalNote': '无长期密钥引用的池项按同节点+算法家族匹配；会话复用实际回收判据'}


def handle_inspection(key, node, inspection, operation, actor, note):
    """Caller holds Node/key/inspection locks. Idempotence never replaces audit."""
    if operation == 'retry':
        rule, severity, action = inspect_key(key, node)
        if inspection.disposition in C.INSPECTION_MANUAL_TERMINALS:
            return {'inspection': inspection_payload(inspection),
                    'recheck': {'rule': rule, 'severity': severity, 'action': action,
                                'preservedManualDisposition': True}}
        if rule:
            inspection.rule, inspection.severity = rule, severity
        inspection.action = action
        inspection.action_at = timezone.now() if action == C.INSPECTION_RESOLVED else None
        disposition = 'rechecked'
    else:
        disposition = {'confirm': 'confirmed', 'dismiss': 'dismissed',
                       'revoke': 'manual_revoked'}[operation]
        if inspection.disposition == disposition:
            return {'inspection': inspection_payload(inspection), 'idempotent': True,
                    'chainHash': ''}
        if inspection.disposition in C.INSPECTION_MANUAL_TERMINALS:
            raise C.ContractError('该记录已人工处置，请查看已处置记录；不可覆盖审计',
                                  code=C.ERR_SESSION_STATE_INVALID)
        # A partial revoke already changed the key. Autoscan/retry can resolve
        # its detection, but an explicit revoke must still finish dependencies.
        recovering_revoke = (operation == 'revoke'
                             and key.status == C.KEY_STATUS_REVOKED
                             and inspection.severity == 'WARNING'
                             and inspection.action == C.INSPECTION_RESOLVED)
        if inspection.action != C.INSPECTION_PENDING_REVIEW and not recovering_revoke:
            raise C.ContractError('仅待复核记录可确认、忽略或人工回收',
                                  code=C.ERR_SESSION_STATE_INVALID)
        if operation == 'revoke':
            if inspection.severity != 'WARNING':
                raise C.ContractError('人工回收仅适用于待复核 WARNING 记录',
                                      code=C.ERR_SESSION_STATE_INVALID)
            result = revoke_long_term_key(node, key.algorithm, key.key_id,
                                          key.key_version, reason=note)
            # Partial revocation is a fact, not a successful disposition. A second
            # revoke request can finish the impact; retry only reruns detection.
            if not result['impact']['sessionsOk']:
                return {**result, 'inspection': inspection_payload(inspection),
                        'partialFailure': True}
            inspection.action = C.INSPECTION_MANUAL_REVOKED
            inspection.action_at = timezone.now()
        elif operation == 'dismiss':
            inspection.action = C.INSPECTION_RESOLVED
            inspection.action_at = timezone.now()
    inspection.disposition = disposition
    inspection.disposition_note = note or None
    inspection.handled_by = str(actor)[:64]
    inspection.handled_at = timezone.now()
    inspection.save(update_fields=['rule', 'severity', 'action', 'action_at',
                                  'disposition', 'disposition_note', 'handled_by', 'handled_at'])
    return {'inspection': inspection_payload(inspection),
            **(result if operation == 'revoke' else {}),
            **({'recheck': {'rule': rule, 'severity': severity, 'action': action}}
               if operation == 'retry' else {})}
