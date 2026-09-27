# -*- coding: utf-8 -*-
"""阶段 6 §7.7：预分配吞吐验收。

    python manage.py benchmark_preallocation --counts 100 1000

计数口径严格按文档 §7.7：
    一条"预分配完成"的 Kyber 池项必须**同时**满足：
      1. SM4 随机密钥已生成；
      2. Kyber 封装/保护已完成；
      3. 对应池项已成功持久化为 READY；
      4. 不包含仍未完成的异步后处理。
    preallocation_rate = READY 成功条数 / 端到端耗时（秒）

**用服务端计时、以成功持久化的条数为准**，不用前端计时、也不把
"发出去的请求数"当分子 —— 后者会把失败算成吞吐。

为什么做成 management command：贴 §7.7 要求的"服务端计时"，
且能直接 `docker exec` 跑，不依赖浏览器。
"""

import time

from django.core.management.base import BaseCommand

from pqkds.key_pool_service import KeyPoolService
from pqkds.models import Node, PreDistributedKey


class Command(BaseCommand):
    help = '预分配吞吐验收（文档 §7.7）：Kyber READY items/s'

    def add_arguments(self, parser):
        parser.add_argument('--counts', nargs='+', type=int, default=[100, 1000],
                            help='每组的条数，例如 --counts 100 1000 5000')
        parser.add_argument('--node-a', default=None, help='节点A的 node_id（默认取前两个节点）')
        parser.add_argument('--node-b', default=None, help='节点B的 node_id')

    def handle(self, *args, **opts):
        counts = opts['counts']

        # 选两个节点做测试对。节点密钥是预分配的前提（要拿接收方公钥封装）。
        if opts['node_a'] and opts['node_b']:
            a = Node.objects.get(node_id=opts['node_a'])
            b = Node.objects.get(node_id=opts['node_b'])
        else:
            nodes = list(Node.objects.filter(status='active')[:2])
            if len(nodes) < 2:
                nodes = list(Node.objects.all()[:2])
            if len(nodes) < 2:
                self.stderr.write('需要至少 2 个节点才能测预分配吞吐')
                return
            a, b = nodes[0], nodes[1]

        self.stdout.write(f'节点对：{a.node_id} ↔ {b.node_id}')
        self.stdout.write(f'Kyber 公钥就绪：A={bool(a.kyber_public_key)} B={bool(b.kyber_public_key)}')
        if not (a.kyber_public_key and b.kyber_public_key):
            self.stderr.write('两个节点都需要 Kyber 公钥才能做预分配 —— '
                              '请先让它们完成首次初始化（/node-self/init/）')
            return

        self.stdout.write('')
        self.stdout.write(f'{"条数":>8} {"成功":>8} {"失败":>8} {"耗时(s)":>10} {"吞吐(条/s)":>12} {"P50(ms)":>10} {"P95(ms)":>10}')
        self.stdout.write('-' * 74)

        summary = []
        for n in counts:
            result = self._run_one(a, b, n)
            summary.append(result)
            self.stdout.write(
                f'{n:>8} {result["ok"]:>8} {result["failed"]:>8} '
                f'{result["seconds"]:>10.3f} {result["rate"]:>12.2f} '
                f'{result["p50"]:>10.2f} {result["p95"]:>10.2f}'
            )

        self.stdout.write('')
        target = 50.0
        for r in summary:
            verdict = '达标' if r['rate'] >= target else '未达标'
            self.stdout.write(f'  {r["count"]} 条：{r["rate"]:.2f} 条/s —— {verdict}（阈值 {target:.0f}）')

        best = max(r['rate'] for r in summary) if summary else 0
        self.stdout.write('')
        self.stdout.write(f'最高吞吐 {best:.2f} 条/s')

    def _run_one(self, node_a, node_b, count):
        """跑一组，返回该组的统计。

        计时**只覆盖生成与持久化**，不含清理 —— 清理是测试的准备工作，
        算进去会低估吞吐，让验收结论偏保守到失真。
        """
        # ⚠️ pool_id 由 generate_kyber_pool **自己生成并返回**，不接受外部传入。
        #    最初按"我先编一个 id 再按它查库"来写，结果查到的永远是 0 行 ——
        #    表现为"吞吐 0，未达标"，看着像性能问题，实则是基准自己找错了行。
        #    必须用返回值里的 pool_id 回查。
        t0 = time.perf_counter()
        result = KeyPoolService.generate_kyber_pool(
            node_a.node_id, node_b.node_id, count=count
        )
        t1 = time.perf_counter()

        pool_id = (result or {}).get('pool_id')
        if not pool_id:
            return {'count': count, 'ok': 0, 'failed': count, 'seconds': t1 - t0,
                    'rate': 0.0, 'p50': 0.0, 'p95': 0.0,
                    'note': f'未返回 pool_id：{str(result)[:120]}'}

        seconds = t1 - t0
        # 以**数据库里实际为 READY 的条数**为准，不用函数返回值 ——
        # 返回的 generated 只说明"函数认为生成了"，不代表真的落库了。
        persisted = PreDistributedKey.objects.filter(pool_id=pool_id, status='READY').count()
        # 兼容旧值：unused 等价于 READY
        if persisted < count:
            persisted += PreDistributedKey.objects.filter(
                pool_id=pool_id, status='unused'
            ).count()

        lat = self._latencies(pool_id)
        rate = (persisted / seconds) if seconds > 0 else 0.0
        return {
            'count': count,
            'ok': persisted,
            'failed': max(0, count - persisted),
            'seconds': seconds,
            'rate': rate,
            'p50': self._pct(lat, 50),
            'p95': self._pct(lat, 95),
        }

    def _latencies(self, pool_id):
        vals = list(
            PreDistributedKey.objects.filter(pool_id=pool_id)
            .exclude(generation_time_ms=None)
            .values_list('generation_time_ms', flat=True)
        )
        return sorted(float(v) for v in vals if v is not None)

    def _pct(self, sorted_vals, p):
        if not sorted_vals:
            return 0.0
        idx = int(len(sorted_vals) * p / 100.0)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]
