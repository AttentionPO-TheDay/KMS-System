# -*- coding: utf-8 -*-
"""KMS-015（计划 §15 第 7 步）：服务端存量私钥的可审计清理。

    # 1) 先看（默认 dry-run，不写任何东西）
    python manage.py clear_node_private_keys

    # 2) 备份（把**值和哈希**落到指定文件；文件权限 0600）
    python manage.py clear_node_private_keys --backup /var/log/kms-private-backup.json

    # 3) 核验并清空（会先逐行比对库内值与备份里的哈希，一致才动手）
    python manage.py clear_node_private_keys --backup /var/log/kms-private-backup.json --clear

<h2>为什么做成这三步而不是一条命令</h2>
计划 §15 明确：**私钥清理是最后一个不可逆步骤**（回滚不能凭空造回已销毁的
私钥）。所以默认动作是"看"，清空要显式 `--clear`，而且**必须**带着
`--backup` —— 没有备份就直接拒。备份文件里存着值和逐列 sha256：
它是"清之前是什么"的唯一答案，也是清空前的核验依据（哈希对不上就中止，
说明备份与库内不是同一份东西）。

<h2>清哪些列、为什么是这些</h2>
`Node` 上的六列服务端私钥材料（KMS-005 起业务上已不再写入，
本命令清的是**存量节点**留下的值）：
    kyber_private_key / gm_private_key / sscl_private_key
    falcon_private_key（CL-Falcon 格材料，概念错误路线）
    falcon_sign_private_key（服务端生成的标准 Falcon 私钥）
    falcon_lattice_params（10.2MB 死字段，无读取方）

⚠️ 清空之后：新链路（KMS-005+）**不受影响** —— 它的私钥只在节点本机；
旧会话模型的端点已由 KMS-015 封存（返回明确的封存码），不依赖这些列。
`Node.<算法>_public_key` **不动**（那是公开量，审计要留）。
"""

import hashlib
import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand

from pqkds.models import Node

#: 要清空的列。顺序即输出顺序。
PRIVATE_COLUMNS = (
    'kyber_private_key',
    'gm_private_key',
    'sscl_private_key',
    'falcon_private_key',
    'falcon_sign_private_key',
    'falcon_lattice_params',
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _snapshot():
    """库内快照：数量 + 每个非空值的 sha256 + 值本身（供备份）。

    ⚠️ 值进内存但不打印：dry-run 的输出里只有哈希与长度 ——
    终端日志、CI 输出都是会被转存的地方，秘密不该出现在那里。
    """
    rows = []
    for node in Node.objects.all().only('id', 'node_id', *PRIVATE_COLUMNS):
        cols = {}
        for name in PRIVATE_COLUMNS:
            value = getattr(node, name, '') or ''
            if value:
                cols[name] = {'length': len(value), 'sha256': _sha256(value), 'value': value}
        if cols:
            rows.append({'nodeId': node.node_id, 'pk': node.pk, 'columns': cols})
    return rows


class Command(BaseCommand):
    help = 'KMS-015：导出（数量+哈希）→ 备份 → 核验 → 清空服务端存量私钥（最后一步不可逆）'

    def add_arguments(self, parser):
        parser.add_argument('--backup', default='', help='备份文件路径（JSON；含值与逐列 sha256）')
        parser.add_argument('--clear', action='store_true',
                            help='真的清空（必须同时给 --backup；不带这个参数只做 dry-run）')

    def handle(self, *args, **opts):
        snapshot = _snapshot()
        total_values = sum(len(r['columns']) for r in snapshot)

        self.stdout.write(f'扫描完成：{len(snapshot)} 个节点仍有服务端私钥材料，共 {total_values} 个非空值。')
        for row in snapshot:
            for name, info in row['columns'].items():
                self.stdout.write(f"  {row['nodeId']}  {name}  {info['length']}B  sha256={info['sha256'][:16]}…")

        if total_values == 0:
            self.stdout.write('没有需要清理的行（服务端已无私钥材料）。' if not opts['clear']
                              else '没有需要清理的行；无需 --clear。')
            return

        if not opts['clear']:
            backup_path = (opts['backup'] or '').strip()
            if not backup_path:
                self.stdout.write('')
                self.stdout.write('这是 dry-run（未写任何东西）。要清理：')
                self.stdout.write('  --backup <文件>           先备份（值 + 哈希）')
                self.stdout.write('  --backup <文件> --clear   核验备份与库内一致后清空　⚠️ 不可逆')
                return
            # ---- 备份：把值与逐列 sha256 落到文件（0600）----
            #
            # ⚠️ 备份文件里是**明文私钥材料**（要用它才能真正回滚），落点必须
            #    是受控位置。容器里推荐 `/var/log/...` —— compose 把
            #    `./dvadmin-logs` 挂在那里，宿主上对应 `kms-ops/dvadmin-logs/`，
            #    且该目录在 `.gitignore` 里（不进提交）。
            #    提示语里把这个对应关系说清楚：容器内的路径直接照抄到宿主上
            #    是找不到文件的 —— 而"备份在哪"正是回滚记录的一半。
            container_path = backup_path
            host_hint = backup_path
            if backup_path.startswith('/var/log/'):
                host_hint = 'kms-ops/dvadmin-logs/' + backup_path[len('/var/log/'):]
            payload = {
                'exportedAt': datetime.now().isoformat(timespec='seconds'),
                'columns': list(PRIVATE_COLUMNS),
                'note': 'KMS-015 私钥清理的备份/回滚记录。含**明文私钥材料**，'
                        '用完请按保密材料处置；恢复前先确认这就是要恢复的那一份。',
                'rows': snapshot,
            }
            directory = os.path.dirname(os.path.abspath(backup_path))
            os.makedirs(directory, exist_ok=True)
            # 先以 0600 建/截断再写，避免默认 umask 短暂地给出过宽权限。
            fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            self.stdout.write('')
            self.stdout.write(
                f'已备份 {len(snapshot)} 个节点、{total_values} 个值 → {container_path}（权限 0600）')
            if host_hint != container_path:
                self.stdout.write(f'  宿主上对应：{host_hint}（kms-ops/dvadmin-logs 是 ./dvadmin-logs 的挂载点）')
            self.stdout.write('下一步（核验一致后清空，⚠️ 不可逆）：')
            self.stdout.write(f'  python manage.py clear_node_private_keys --backup {container_path} --clear')
            return

        backup_path = (opts['backup'] or '').strip()
        if not backup_path:
            # 计划 §15：没有备份就没有回滚记录，直接拒 —— 不提供"裸清空"。
            self.stderr.write('拒绝执行 --clear：必须同时给 --backup <文件>。'
                              '（私钥清理不可逆，备份是唯一的回滚记录）')
            return

        # ---- 核验：备份文件必须与**此刻的库内**是同一份东西 ----
        if not os.path.exists(backup_path):
            self.stderr.write(f'拒绝执行 --clear：备份文件不存在 {backup_path}（先跑一次 --backup）')
            return
        with open(backup_path, 'r', encoding='utf-8') as fh:
            backup = json.load(fh)
        backup_rows = {r['nodeId']: r for r in backup.get('rows', [])}
        mismatches = []
        for row in snapshot:
            saved = backup_rows.get(row['nodeId'])
            if not saved:
                mismatches.append(f"{row['nodeId']}：备份里没有这个节点")
                continue
            for name, info in row['columns'].items():
                saved_col = (saved.get('columns') or {}).get(name) or {}
                if saved_col.get('sha256') != info['sha256']:
                    mismatches.append(f"{row['nodeId']}.{name}：库内 {info['sha256'][:12]}… ≠ 备份 {str(saved_col.get('sha256'))[:12]}…")
        if mismatches:
            # 哈希对不上时中止：说明备份与库内不是同一份 —— 此时清空会
            # 留下"以为备份了、实际没备"的记录，比不清更糟。
            self.stderr.write('拒绝执行 --clear：备份与库内不一致，逐条如下（重新备份后再试）：')
            for line in mismatches:
                self.stderr.write(f'  {line}')
            return

        # ---- 清空（逐行 expliclit，可审计的条数）----
        cleared_nodes = 0
        for row in snapshot:
            fields = [name for name in PRIVATE_COLUMNS if name in row['columns']]
            if not fields:
                continue
            Node.objects.filter(pk=row['pk']).update(**{name: '' for name in fields})
            cleared_nodes += 1

        self.stdout.write('')
        self.stdout.write(f'已清空：{cleared_nodes} 个节点、{total_values} 个值。')
        self.stdout.write(f'回滚记录：清空前的值与逐列 sha256 在 {backup_path}'
                          f'（备份时间 {backup.get("exportedAt", "未知")}）。')
        self.stdout.write('⚠️ 计划 §15：这是最后一个不可逆步骤 —— 回滚需要人工用备份恢复，'
                          '而恢复本身也是一次写库操作，请走变更流程。')