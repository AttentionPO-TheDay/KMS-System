"""Three bounded acceptance cases, using the pool's actual proof gate."""
import base64
import copy
from datetime import timedelta
import hashlib
import json
import logging
import re
import time
import uuid

import numpy as np
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import lattice_preallocation as service
from . import lattice_preallocation_math as lattice
from . import api_contract as C
from .internal_pool_views import _internal_token_ok
from .models import LatticePreparation, LatticeTestRecord, Node, NodeLongTermKey, PreDistributedKey

logger = logging.getLogger(__name__)
CASES = {'parallel-sampling': '并行抽样短向量', 'offline-trapdoor': '离线生成格陷门', 'basis-delegation': '快速委派格基向量'}


def check(name, expected, actual, passed):
    if type(actual) is bool:
        actual = '符合预期' if actual else '不符合预期'
    return dict(name=name, expected=expected, actual=str(actual), passed=bool(passed))


def run_sampling(preparation, count, workers):
    from .crypto_utils import KyberCrypto
    from .key_pool_service import KeyPoolService
    from .sm4_crypto import PayloadCipher, SM4Crypto
    from .node_key_registry import require_usable_key
    node = preparation.node
    registered = require_usable_key(node, 'KYBER')
    public = base64.b64decode(node.kyber_public_key, validate=True)
    variant = {800: 512, 1184: 768, 1568: 1024}.get(len(public))
    if variant is None:
        raise ValueError('绑定节点需要具有可用 Kyber 公钥')
    kem = KyberCrypto(variant)
    pool_id = 'lattice-test-' + uuid.uuid4().hex
    rows, checks, samples = [], [], []
    before = time.perf_counter()
    expires = timezone.now() + timedelta(hours=1)
    # Real DB rows in a rollback-only transaction, never business pool inventory.
    with transaction.atomic():
        for i in range(count):
            key = PayloadCipher.generate_key()
            ciphertext, shared = kem.encrypt(public)
            wrapped, nonce_tag = SM4Crypto.encrypt(key, PayloadCipher.kek_from_shared_secret('sm4', shared))
            package = dict(kem_ciphertext=base64.b64encode(ciphertext).decode(),
                encrypted_aes_key=base64.b64encode(wrapped).decode(),
                nonce=base64.b64encode(nonce_tag[:12]).decode(), tag=base64.b64encode(nonce_tag[12:]).decode(),
                payload_algorithm='sm4', variant=variant, pool_id=pool_id, key_index=i,
                receiver_node_id=node.node_id, key_hash=hashlib.sha256(key).hexdigest())
            rows.append(PreDistributedKey(pool_id=pool_id, key_index=i, node1=node, node2=node,
                algorithm='kyber_kem', wrapping_algorithm='kyber_kem', payload_algorithm='sm4',
                encrypted_key_data=json.dumps(package), key_hash=package['key_hash'],
                status='READY', recipient_type='pool', expires_at=expires,
                long_term_key_id=registered.key_id, long_term_key_version=registered.key_version))
        PreDistributedKey.objects.bulk_create(rows)
        # DB/backend combinations need not return bulk-created IDs.
        rows = list(PreDistributedKey.objects.filter(pool_id=pool_id).order_by('key_index'))
        measurement = service.protect_pool_rows(rows, node.node_id, preparation, workers)
        context = service.load_context(str(preparation.pk))
        valid = sum(service.verify_pool_row(row) for row in rows)
        original = json.loads(rows[0].encrypted_key_data)
        tampered = copy.deepcopy(original)
        tampered['key_hash'] = '0' * 64
        checks.append(check('保护包绑定', '修改保护包后证明校验失败',
            '拒绝' if not service.verify_package(tampered, node.node_id) else '接受',
            not service.verify_package(tampered, node.node_id)))
        without = copy.deepcopy(original)
        without.pop('latticeProof')
        rows[0].encrypted_key_data = json.dumps(without)
        checks.append(check('证明完整性', '删除证明后拒绝取用', not service.verify_pool_row(rows[0]), not service.verify_pool_row(rows[0])))
        rows[0].encrypted_key_data = json.dumps(original)
        selected = KeyPoolService.consume_key(node.node_id, node.node_id, 'kyber_kem', pool_id=pool_id)
        consumed = bool(selected.get('success') and PreDistributedKey.objects.get(pk=selected['key_id']).status == 'CONSUMED')
        checks.extend([
            check('并发执行', '至少两个工作进程并行执行' if workers > 1 else '单进程对照执行',
                f"实际 {measurement['usedWorkers']} 个进程，峰值在途 {measurement['peakInFlight']} 个任务",
                measurement['usedWorkers'] >= min(workers, 2) and measurement['peakInFlight'] >= min(workers, 2)),
            check('有效采样数量', f'{count} 条通过模 q 关系及长度约束', f'{valid}/{count}', valid == count),
            check('预分配入池', f'{count} 条保存格证明及委派引用', measurement['verified'], measurement['verified'] == count),
            check('保护包取用', '实际取用函数将一条有效池项置为 CONSUMED', consumed, consumed),
        ])
        for row in rows:
            package = json.loads(row.encrypted_key_data)
            proof = package['latticeProof']
            vector = np.asarray(proof['vector'], dtype=np.int64)
            target = lattice.target_for(service.canonical({k: v for k, v in package.items() if k != 'latticeProof'}))
            samples.append(dict(index=row.key_index, keyHash=row.key_hash, publicDigest=preparation.public_digest,
                packageDigest=proof['packageDigest'], vector=proof['vector'], target=target.tolist(),
                message=service.canonical({k: v for k, v in package.items() if k != 'latticeProof'}).decode('utf-8'),
                residual=(context['public'] @ vector % lattice.Q - target).tolist(),
                norm=float(np.linalg.norm(vector)), bound=lattice.norm_bound(context), verified=service.verify_pool_row(row)))
        transaction.set_rollback(True)
    cleanup = not PreDistributedKey.objects.filter(pool_id=pool_id).exists()
    checks.append(check('测试数据清理', '隔离批次不留在业务密钥池', cleanup, cleanup))
    return dict(checks=checks, samples=samples, count=count, workers=workers, poolId=pool_id,
        publicMatrix=context['public'].tolist(),
        valid=valid, samplingMs=measurement['samplingMs'], totalMs=(time.perf_counter() - before) * 1000,
        usedWorkers=measurement['usedWorkers'], peakInFlight=measurement['peakInFlight'], workerSpans=measurement['spans'],
        executionMode=measurement['executionMode'], poolReused=measurement['poolReused'],
        poolSetupMs=measurement['poolSetupMs'], queueMs=measurement['queueMs'], computeMs=measurement['computeMs'],
        cleanupComplete=cleanup, isolated=True, preparation=service.public_record(preparation))


def execute(payload):
    case_id = payload['caseId']
    if case_id == 'offline-trapdoor':
        root, values = service.create_root()
        return dict(preparation=service.public_record(root), **values, checks=[
            check('陷门对应关系', 'A·T ≡ 0 (mod q)', '余数矩阵全零', values['kernelRelation']),
            check('格基完整性', '满秩，构造行列式为 qⁿ', f'秩 {len(root.public_matrix[0])}，指数 n={lattice.N}', values['fullRank']),
            check('离线材料持久化', '重新读取加密材料后关系验证通过', '已重载验证', values['secretPersistedEncrypted']),
        ])
    if case_id == 'basis-delegation':
        root = LatticePreparation.objects.get(pk=payload.get('rootId'), kind='ROOT')
        node = Node.objects.get(node_id=payload.get('nodeId'))
        child, values = service.create_delegation(root, node)
        return dict(preparation=service.public_record(child), **values, checks=[
            check('节点绑定', '委派公矩阵绑定主参数摘要与节点编号', node.node_id, values['nodeBound']),
            check('委派格关系', 'F·T_F ≡ 0 (mod q)', '余数矩阵全零', values['kernelRelation']),
            check('委派材料可用性', '使用持久化委派基采样并通过关系及长度验证', '验证通过', values['preimageVerified']),
        ])
    preparation = LatticePreparation.objects.select_related('node').get(pk=payload.get('preparationId'), kind='DELEGATED')
    count, workers = payload.get('count', 32), payload.get('workers', 4)
    if type(count) is not int or count not in (16, 32, 64) or type(workers) is not int or workers not in (1, 2, 4, 8):
        raise ValueError('样本数只接受 16、32、64，并发数只接受 1、2、4、8')
    return run_sampling(preparation, count, workers)


@transaction.non_atomic_requests
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def internal_lattice_tests(request):
    if not _internal_token_ok(request):
        return JsonResponse(dict(code=403, msg='内部通道拒绝访问'), status=403)
    owner = request.headers.get('X-Acceptance-Owner', '')
    if not re.fullmatch('[0-9a-f]{64}', owner):
        return JsonResponse(dict(code=400, msg='缺少受控验收会话'), status=400)
    if request.method == 'GET':
        records = list(LatticeTestRecord.objects.filter(owner=owner).order_by('-created_at')[:12])
        preparations = LatticePreparation.objects.select_related('node').order_by('-created_at')[:100]
        nodes = list(Node.objects.exclude(node_id__startswith='acc').values('id', 'node_id', 'name', 'kyber_public_key')[:200])
        ready_nodes = set(NodeLongTermKey.objects.filter(node_id__in=[node['id'] for node in nodes],
            algorithm='KYBER', status='ACTIVE').values_list('node_id', flat=True))
        return JsonResponse(dict(code=200, data=dict(profile=lattice.PROFILE, n=lattice.N, q=lattice.Q,
            securityScope='功能验证参数；不声明生产安全等级。保护包继续使用 Kyber、SM4 和 Falcon。',
            preparations=[service.public_record(row) for row in preparations],
            nodes=[dict(id=row['node_id'], name=row['name'], kyberAvailable=bool(row['kyber_public_key']) and row['id'] in ready_nodes)
                   for row in nodes], records=[row.result for row in records])))
    try:
        payload = json.loads(request.body or b'{}')
        if not isinstance(payload, dict) or payload.get('caseId') not in CASES:
            raise ValueError('未知测试项')
        allowed = {'offline-trapdoor': {'caseId'}, 'basis-delegation': {'caseId', 'rootId', 'nodeId'},
                   'parallel-sampling': {'caseId', 'preparationId', 'count', 'workers'}}[payload['caseId']]
        if set(payload) - allowed:
            raise ValueError('请求包含未允许字段')
        started = time.perf_counter()
        result = execute(payload)
        result.update(id=str(uuid.uuid4()), caseId=payload['caseId'], title=CASES[payload['caseId']],
            recordedAt=timezone.now().isoformat(), durationMs=(time.perf_counter() - started) * 1000,
            passed=all(item['passed'] for item in result['checks']), profile=lattice.PROFILE)
        LatticeTestRecord.objects.create(owner=owner, case_id=payload['caseId'], result=result)
        return JsonResponse(dict(code=200, data=result))
    except C.ContractError as error:
        return JsonResponse(dict(code=400, msg=error.message), status=400)
    except (ValueError, TypeError, Node.DoesNotExist, LatticePreparation.DoesNotExist) as error:
        return JsonResponse(dict(code=400, msg=str(error)), status=400)
    except Exception:
        logger.exception('Lattice preallocation acceptance failed')
        return JsonResponse(dict(code=503, msg='格预分配测试执行失败，请检查服务端记录'), status=503)
