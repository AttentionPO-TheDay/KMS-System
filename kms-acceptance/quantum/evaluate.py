"""Fixed Kyber round-3 LWE estimates, never a production-key attack or verdict."""
import math
import time
from datetime import datetime, timezone

from circuit import simulate

ESTIMATOR_COMMIT = 'e4333d9bf9ef42fd8a29651b0c559fba7ce0d834'
CASES = {
    'quantum-lwe-usvp': ('primal_usvp', '原始格 uSVP 攻击成本评估'),
    'quantum-lwe-bdd': ('primal_bdd', '原始格 BDD 攻击成本评估'),
    'quantum-lwe-dual': ('dual', '对偶格攻击成本评估'),
}


def evaluate(case_id):
    if case_id not in CASES:
        raise ValueError('Unknown fixed model')
    from estimator import LWE, schemes
    from estimator.reduction import ADPS16
    from sage.all import log, version

    started = time.perf_counter()
    method, name = CASES[case_id]
    circuit = simulate()
    estimates = []
    for variant in (512, 768, 1024):
        params = getattr(schemes, f'Kyber{variant}')
        tick = time.perf_counter()
        cost = getattr(LWE, method)(params, red_cost_model=ADPS16(mode='quantum'))
        bits = float(log(cost['rop'], 2))
        if not math.isfinite(bits) or bits <= 0:
            raise ValueError('No finite estimate')
        estimates.append({
            'variant': variant, 'n': int(params.n), 'q': int(params.q), 'm': int(params.m),
            'secretDistribution': str(params.Xs), 'errorDistribution': str(params.Xe),
            'log2Rop': bits, 'beta': int(cost['beta']), 'rawCost': str(cost),
            'durationMs': round((time.perf_counter() - tick) * 1000, 3),
        })
    return {
        'version': 1, 'caseId': case_id, 'model': method, 'name': name,
        'recordedAt': datetime.now(timezone.utc).isoformat(),
        'durationMs': round((time.perf_counter() - started) * 1000, 3),
        'estimatorCommit': ESTIMATOR_COMMIT, 'sageVersion': version(),
        'costModel': 'ADPS16(mode=quantum): Core-SVP reduction cost 2^(0.265*beta)',
        'circuit': circuit, 'estimates': estimates, 'evaluationComplete': circuit['verified'],
        'acceptancePassed': False,
        'scope': '量子辅助格归约的启发式成本评估；rop为模型运算量，不是秒数、量子门数或安全证明。采用Kyber round-3公开参数并忽略压缩，不评估完整KEM、自定义协议或全部攻击。三种模型不自动等于任务书认可的三种量子攻击。',
        'references': [
            f'https://github.com/malb/lattice-estimator/tree/{ESTIMATOR_COMMIT}',
            'https://pq-crystals.org/kyber/data/kyber-specification-round3-20210804.pdf',
            'https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/alkim',
        ],
    }


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('--case-id', choices=CASES, required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    result = evaluate(args.case_id)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'caseId': result['caseId'], 'evaluationComplete': result['evaluationComplete'],
                          'log2Rop': [r['log2Rop'] for r in result['estimates']]}))
    else:
        print(json.dumps(result, ensure_ascii=False))
