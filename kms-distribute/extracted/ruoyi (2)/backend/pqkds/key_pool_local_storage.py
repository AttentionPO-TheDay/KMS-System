# -*- coding: utf-8 -*-
"""
节点本地密钥池存储模块

节点从 KDS 下载加密的密钥池数据包后，用自己的 Kyber 私钥解密，
将明文 AES 会话密钥保存到本地 JSON 文件。
建立会话时从本地文件中取用一条密钥。

文件结构:
  node_key_pools/
    {node_id}/
      pool_{pool_id}.json   ← 单个密钥池文件

每个 pool 文件内容:
{
  "pool_id": "...",
  "node_id": "node_alice",
  "peer_node_id": "node_bob",
  "algorithm": "kyber_kem",
  "created_at": "2025-01-01T00:00:00",
  "expires_at": "2025-01-02T00:00:00",
  "keys": [
    {"index": 0, "key_hex": "aabbcc...", "key_hash": "sha256...", "used": false},
    {"index": 1, "key_hex": "ddeeff...", "key_hash": "sha256...", "used": false},
    ...
  ]
}

载荷算法与 key_hex 长度（决策 D3）
---------------------------------
对称载荷层已从 **AES-256 换成国密 SM4**，因此 `key_hex` 的长度也变了：

===========================  ==================  ==========================
算法                          key_hex 长度        说明
===========================  ==================  ==========================
SM4（新写入）                 **32** 字符（16B）  2026-09 之后生成的池
AES-256（历史）               **64** 字符（32B）  更早生成的池，仍须可读可用
===========================  ==================  ==========================

**读取时两种长度都要接受**（计划 P2 的硬性验证项之一：旧池仍可读取与使用）。
本模块不按长度猜算法 —— 那是加解密层的事（`sm4_crypto.PayloadCipher` 按长度分派）。
这里只负责**校验长度合法**，让"文件被截断/写坏"这类问题在取用点就带着
pool_id 与 index 报出来，而不是等到解密时才以一句难以定位的密码学错误收场。
"""
import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 默认存储根目录：项目 backend/ 下的 node_key_pools/
_STORAGE_ROOT = Path(__file__).resolve().parent.parent / 'node_key_pools'


def _get_node_dir(node_id: str) -> Path:
    """获取节点的密钥池目录，不存在则创建"""
    d = _STORAGE_ROOT / node_id
    d.mkdir(parents=True, exist_ok=True)
    return d


#: 合法的载荷密钥长度（字节）：16 = SM4（新），32 = 历史 AES-256
_ACCEPTED_KEY_BYTES = (16, 32)


def payload_key_of(key_entry: Dict[str, Any], context: str = "") -> bytes:
    """把一条本地池记录的 `key_hex` 解成字节，并校验长度。

    两种长度都接受：
      * **16 字节** → SM4（2026-09 之后生成的池）
      * **32 字节** → AES-256（历史池，仍须可用）

    校验放在这里而不是等到解密：一旦文件被截断或写坏，我们希望错误信息里
    带着"哪个池、第几条"，而不是让调用方在几百行之外收到一句密码学异常。
    """
    raw = (key_entry or {}).get('key_hex') or ''
    where = context or f"index={key_entry.get('index') if key_entry else '?'}"
    if not raw:
        raise ValueError(f"本地密钥池记录缺少 key_hex（{where}）")
    try:
        data = bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"本地密钥池 key_hex 不是合法十六进制（{where}）: {exc}") from exc
    if len(data) not in _ACCEPTED_KEY_BYTES:
        raise ValueError(
            f"本地密钥池 key_hex 长度非法（{where}）：解出 {len(data)} 字节，"
            f"应为 16（SM4）或 32（历史 AES-256）。"
            f"若是文件被截断，请重新分发该池。"
        )
    return data


def key_algorithm_of(key_entry: Dict[str, Any]) -> str:
    """该条记录对应的载荷算法（按长度判断，用于日志与排查）。"""
    length = len(payload_key_of(key_entry))
    return 'sm4' if length == 16 else 'aes_256'


def save_pool_to_local(
    node_id: str,
    peer_node_id: str,
    pool_id: str,
    algorithm: str,
    keys: List[Dict[str, Any]],
    expires_at: str,
) -> Dict[str, Any]:
    """
    将解密后的密钥池保存到节点本地文件。

    Args:
        node_id: 本节点 ID
        peer_node_id: 对端节点 ID
        pool_id: 密钥池批次 ID
        algorithm: 加密算法标识
        keys: 密钥列表，每条 {"index": int, "key_hex": str, "key_hash": str}
        expires_at: 过期时间 ISO 格式

    Returns:
        {"success": True, "file_path": "...", "count": N}
    """
    node_dir = _get_node_dir(node_id)
    file_path = node_dir / f"pool_{pool_id}.json"

    pool_data = {
        'pool_id': pool_id,
        'node_id': node_id,
        'peer_node_id': peer_node_id,
        'algorithm': algorithm,
        'created_at': datetime.utcnow().isoformat(),
        'expires_at': expires_at,
        'keys': [
            {**k, 'used': False} for k in keys
        ],
    }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(pool_data, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[LocalPool] 节点 {node_id} 保存密钥池 {pool_id}: "
        f"{len(keys)} 条密钥 → {file_path}"
    )
    return {
        'success': True,
        'file_path': str(file_path),
        'count': len(keys),
    }


def consume_key_from_local(
    node_id: str,
    peer_node_id: str,
    algorithm: str = None,
) -> Optional[Dict[str, Any]]:
    """
    从发送方节点的本地密钥池中取用一条未使用、未过期的密钥。

    密钥池是单向的：node_id → peer_node_id 方向。
    只在 node_id 的本地目录中查找 peer_node_id 为目标的池。

    Args:
        node_id: 发送方节点 ID（密钥池持有者）
        peer_node_id: 接收方节点 ID（通信目标）
        algorithm: 可选，筛选算法类型

    Returns:
        {"pool_id", "key_index", "key_hex", "key_hash", "algorithm"} 或 None
    """
    node_dir = _get_node_dir(node_id)
    now = datetime.utcnow().isoformat()

    # 遍历发送方的所有池文件，找到目标为 peer_node_id 的池
    for pool_file in sorted(node_dir.glob('pool_*.json')):
        try:
            with open(pool_file, 'r', encoding='utf-8') as f:
                pool_data = json.load(f)
        except Exception:
            continue

        # 匹配接收方节点
        if pool_data.get('peer_node_id') != peer_node_id:
            continue
        # 匹配算法
        if algorithm and pool_data.get('algorithm') != algorithm:
            continue
        # 检查过期
        if pool_data.get('expires_at', '') < now:
            continue

        # 找第一条未使用的密钥
        for key_entry in pool_data['keys']:
            if key_entry.get('used'):
                continue

            # 取用前校验 key_hex 长度（16=SM4 / 32=历史 AES-256）。
            # 写坏的条目直接跳过并告警，不要让它在解密阶段变成难以定位的错误。
            try:
                payload_key_of(key_entry, context=f"{pool_data.get('pool_id')}#{key_entry.get('index')}")
            except ValueError as exc:
                logger.warning(f"[LocalPool] 跳过损坏的密钥条目: {exc}")
                continue

            # 标记为已使用并写回文件
            key_entry['used'] = True
            key_entry['used_at'] = datetime.utcnow().isoformat()
            with open(pool_file, 'w', encoding='utf-8') as f:
                json.dump(pool_data, f, ensure_ascii=False, indent=2)

            logger.info(
                f"[LocalPool] 节点 {node_id} 取用密钥: "
                f"pool={pool_data['pool_id']}#{key_entry['index']} "
                f"({key_algorithm_of(key_entry)})"
            )
            return {
                'pool_id': pool_data['pool_id'],
                'key_index': key_entry['index'],
                'key_hex': key_entry['key_hex'],
                'key_hash': key_entry['key_hash'],
                'algorithm': pool_data['algorithm'],
            }

    return None


def get_local_pool_stats(node_id: str) -> Dict[str, Any]:
    """
    获取节点本地密钥池的统计信息。

    Returns:
        {"total": N, "unused": N, "used": N, "expired": N, "pools": [...]}
    """
    node_dir = _get_node_dir(node_id)
    now = datetime.utcnow().isoformat()

    total = 0
    unused = 0
    used = 0
    expired_count = 0
    pools = []

    for pool_file in sorted(node_dir.glob('pool_*.json')):
        try:
            with open(pool_file, 'r', encoding='utf-8') as f:
                pool_data = json.load(f)
        except Exception:
            continue

        is_expired = pool_data.get('expires_at', '') < now
        pool_total = len(pool_data.get('keys', []))
        pool_used = sum(1 for k in pool_data.get('keys', []) if k.get('used'))
        pool_unused = pool_total - pool_used

        total += pool_total
        used += pool_used
        if is_expired:
            expired_count += pool_unused
        else:
            unused += pool_unused

        pools.append({
            'pool_id': pool_data.get('pool_id'),
            'peer_node_id': pool_data.get('peer_node_id'),
            'algorithm': pool_data.get('algorithm'),
            'total': pool_total,
            'unused': pool_unused if not is_expired else 0,
            'used': pool_used,
            'expired': is_expired,
            'expires_at': pool_data.get('expires_at'),
        })

    return {
        'node_id': node_id,
        'total': total,
        'unused': unused,
        'used': used,
        'expired': expired_count,
        'pools': pools,
    }


def cleanup_expired_local_pools() -> int:
    """
    清理所有节点本地目录中已过期的密钥池文件。
    - 整个池过期 → 删除文件
    - 池未过期但部分密钥已用完 → 保留（不删）

    Returns:
        删除的文件数量
    """
    deleted = 0
    now = datetime.utcnow().isoformat()

    if not _STORAGE_ROOT.exists():
        return 0

    for node_dir in _STORAGE_ROOT.iterdir():
        if not node_dir.is_dir():
            continue
        for pool_file in list(node_dir.glob('pool_*.json')):
            try:
                with open(pool_file, 'r', encoding='utf-8') as f:
                    pool_data = json.load(f)
                expires_at = pool_data.get('expires_at', '')
                if expires_at and expires_at < now:
                    pool_file.unlink()
                    deleted += 1
                    logger.info(
                        f"[LocalPool] 删除过期密钥池文件: {pool_file.name} "
                        f"(node={node_dir.name}, expired={expires_at})"
                    )
            except Exception as e:
                logger.warning(f"[LocalPool] 清理文件 {pool_file} 失败: {e}")
                continue

    logger.info(f"[LocalPool] 过期清理完成: 删除 {deleted} 个文件")
    return deleted