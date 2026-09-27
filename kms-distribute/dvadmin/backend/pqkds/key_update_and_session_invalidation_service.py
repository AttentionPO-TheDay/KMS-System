import logging
import hashlib
from django.utils import timezone
from django.db import transaction, models
from typing import Dict, Any, List, Tuple
from .models import (
    Node, SessionKey, NodeKeyVersion, SessionKeyInvalidation,
    KeyDistributionLog, FalconKeyPair
)
logger = logging.getLogger(__name__)
class KeyUpdateAndSessionInvalidationService:
    def __init__(self, node_id: str):
        self.node_id = node_id
        try:
            self.node = Node.objects.get(node_id=node_id)
        except Node.DoesNotExist:
            raise ValueError(f"节点 {node_id} 不存在")
    @staticmethod
    def _calculate_public_key_hash(public_key_str: str) -> str:
        return hashlib.sha256(public_key_str.encode()).hexdigest()
    def _get_or_create_key_version(self) -> NodeKeyVersion:
        try:
            key_version = NodeKeyVersion.objects.get(node=self.node)
        except NodeKeyVersion.DoesNotExist:
            key_version = NodeKeyVersion.objects.create(
                node=self.node,
                kyber_version=1,
                falcon_version=1,
                kyber_public_key_hash='',
                falcon_public_key_hash=''
            )
            logger.info(f"为节点 {self.node_id} 创建新的密钥版本记录")
        return key_version
    def _check_kyber_key_updated(self, current_kyber_hash: str) -> bool:
        key_version = self._get_or_create_key_version()
        if not key_version.kyber_public_key_hash:
            return True
        if key_version.kyber_public_key_hash != current_kyber_hash:
            return True
        return False
    def _check_falcon_key_updated(self, current_falcon_hash: str) -> bool:
        key_version = self._get_or_create_key_version()
        if not key_version.falcon_public_key_hash:
            return True
        if key_version.falcon_public_key_hash != current_falcon_hash:
            return True
        return False
    def _update_key_versions(self, kyber_hash: str, falcon_hash: str) -> Tuple[int, int]:
        key_version = self._get_or_create_key_version()
        kyber_version_before = key_version.kyber_version
        falcon_version_before = key_version.falcon_version
        if key_version.kyber_public_key_hash != kyber_hash and key_version.kyber_public_key_hash:
            key_version.kyber_version += 1
        if key_version.falcon_public_key_hash != falcon_hash and key_version.falcon_public_key_hash:
            key_version.falcon_version += 1
        key_version.kyber_public_key_hash = kyber_hash
        key_version.falcon_public_key_hash = falcon_hash
        key_version.save()
        logger.info(
            f"节点 {self.node_id} 密钥版本已更新: "
            f"Kyber {kyber_version_before} → {key_version.kyber_version}, "
            f"Falcon {falcon_version_before} → {key_version.falcon_version}"
        )
        return kyber_version_before, falcon_version_before
    @transaction.atomic
    def invalidate_sessions_on_kyber_key_update(self) -> Dict[str, Any]:
        logger.info(f"开始处理节点 {self.node_id} 的Kyber密钥更新导致的会话失效")
        current_kyber_hash = self._calculate_public_key_hash(self.node.kyber_public_key)
        if not self._check_kyber_key_updated(current_kyber_hash):
            logger.info(f"节点 {self.node_id} 的Kyber密钥未更新，跳过会话失效处理")
            return {
                'success': True,
                'message': 'Kyber密钥未更新',
                'invalidated_sessions': 0
            }
        active_sessions = SessionKey.objects.filter(
            status__in=['initiated', 'established', 'blockchain_recorded'],
            expires_at__gt=timezone.now()
        ).filter(
            models.Q(node1=self.node) | models.Q(node2=self.node)
        )
        invalidated_count = 0
        invalidated_session_ids = []
        for session in active_sessions:
            try:
                if session.node1 == self.node:
                    reason = 'node1_key_updated'
                    invalidated_node = self.node
                else:
                    reason = 'node2_key_updated'
                    invalidated_node = self.node
                kyber_ver_before, falcon_ver_before = self._update_key_versions(
                    current_kyber_hash, 
                    self._calculate_public_key_hash(self.node.falcon_public_key)
                )
                key_version = self._get_or_create_key_version()
                SessionKeyInvalidation.objects.create(
                    session=session,
                    invalidated_node=invalidated_node,
                    reason=reason,
                    kyber_version_before=kyber_ver_before,
                    falcon_version_before=falcon_ver_before,
                    kyber_version_after=key_version.kyber_version,
                    falcon_version_after=key_version.falcon_version
                )
                session.status = 'revoked'
                session.save()
                invalidated_count += 1
                invalidated_session_ids.append(session.session_id)
                logger.info(f"会话 {session.session_id} 已因Kyber密钥更新而失效")
            except Exception as e:
                logger.error(f"处理会话 {session.session_id} 失效时出错: {str(e)}")
                continue
        logger.info(f"节点 {self.node_id} 的Kyber密钥更新导致 {invalidated_count} 个会话失效")
        return {
            'success': True,
            'message': f'已失效 {invalidated_count} 个会话',
            'invalidated_sessions': invalidated_count,
            'invalidated_session_ids': invalidated_session_ids
        }
    @transaction.atomic
    def invalidate_sessions_on_falcon_key_update(self) -> Dict[str, Any]:
        logger.info(f"开始处理节点 {self.node_id} 的Falcon密钥更新导致的会话失效")
        current_falcon_hash = self._calculate_public_key_hash(self.node.falcon_public_key)
        if not self._check_falcon_key_updated(current_falcon_hash):
            logger.info(f"节点 {self.node_id} 的Falcon密钥未更新，跳过会话失效处理")
            return {
                'success': True,
                'message': 'Falcon密钥未更新',
                'invalidated_sessions': 0
            }
        active_sessions = SessionKey.objects.filter(
            status__in=['initiated', 'established', 'blockchain_recorded'],
            expires_at__gt=timezone.now()
        ).filter(
            models.Q(node1=self.node) | models.Q(node2=self.node)
        )
        invalidated_count = 0
        invalidated_session_ids = []
        for session in active_sessions:
            try:
                if session.node1 == self.node:
                    reason = 'node1_key_updated'
                    invalidated_node = self.node
                else:
                    reason = 'node2_key_updated'
                    invalidated_node = self.node
                kyber_ver_before, falcon_ver_before = self._update_key_versions(
                    self._calculate_public_key_hash(self.node.kyber_public_key),
                    current_falcon_hash
                )
                key_version = self._get_or_create_key_version()
                SessionKeyInvalidation.objects.create(
                    session=session,
                    invalidated_node=invalidated_node,
                    reason=reason,
                    kyber_version_before=kyber_ver_before,
                    falcon_version_before=falcon_ver_before,
                    kyber_version_after=key_version.kyber_version,
                    falcon_version_after=key_version.falcon_version
                )
                session.status = 'revoked'
                session.save()
                invalidated_count += 1
                invalidated_session_ids.append(session.session_id)
                logger.info(f"会话 {session.session_id} 已因Falcon密钥更新而失效")
            except Exception as e:
                logger.error(f"处理会话 {session.session_id} 失效时出错: {str(e)}")
                continue
        logger.info(f"节点 {self.node_id} 的Falcon密钥更新导致 {invalidated_count} 个会话失效")
        return {
            'success': True,
            'message': f'已失效 {invalidated_count} 个会话',
            'invalidated_sessions': invalidated_count,
            'invalidated_session_ids': invalidated_session_ids
        }
    @transaction.atomic
    def invalidate_sessions_on_both_keys_update(self) -> Dict[str, Any]:
        logger.info(f"开始处理节点 {self.node_id} 的双密钥更新导致的会话失效")
        current_kyber_hash = self._calculate_public_key_hash(self.node.kyber_public_key)
        current_falcon_hash = self._calculate_public_key_hash(self.node.falcon_public_key)
        kyber_updated = self._check_kyber_key_updated(current_kyber_hash)
        falcon_updated = self._check_falcon_key_updated(current_falcon_hash)
        if not kyber_updated and not falcon_updated:
            logger.info(f"节点 {self.node_id} 的密钥未更新，跳过会话失效处理")
            return {
                'success': True,
                'message': '密钥未更新',
                'invalidated_sessions': 0
            }
        active_sessions = SessionKey.objects.filter(
            status__in=['initiated', 'established', 'blockchain_recorded'],
            expires_at__gt=timezone.now()
        ).filter(
            models.Q(node1=self.node) | models.Q(node2=self.node)
        )
        invalidated_count = 0
        invalidated_session_ids = []
        for session in active_sessions:
            try:
                if kyber_updated and falcon_updated:
                    reason = 'both_keys_updated'
                elif kyber_updated:
                    reason = 'node1_key_updated' if session.node1 == self.node else 'node2_key_updated'
                else:
                    reason = 'node1_key_updated' if session.node1 == self.node else 'node2_key_updated'
                invalidated_node = self.node
                kyber_ver_before, falcon_ver_before = self._update_key_versions(
                    current_kyber_hash,
                    current_falcon_hash
                )
                key_version = self._get_or_create_key_version()
                SessionKeyInvalidation.objects.create(
                    session=session,
                    invalidated_node=invalidated_node,
                    reason=reason,
                    kyber_version_before=kyber_ver_before,
                    falcon_version_before=falcon_ver_before,
                    kyber_version_after=key_version.kyber_version,
                    falcon_version_after=key_version.falcon_version
                )
                session.status = 'revoked'
                session.save()
                invalidated_count += 1
                invalidated_session_ids.append(session.session_id)
                logger.info(f"会话 {session.session_id} 已因双密钥更新而失效")
            except Exception as e:
                logger.error(f"处理会话 {session.session_id} 失效时出错: {str(e)}")
                continue
        logger.info(f"节点 {self.node_id} 的双密钥更新导致 {invalidated_count} 个会话失效")
        return {
            'success': True,
            'message': f'已失效 {invalidated_count} 个会话',
            'invalidated_sessions': invalidated_count,
            'invalidated_session_ids': invalidated_session_ids
        }