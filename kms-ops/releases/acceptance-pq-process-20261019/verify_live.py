"""Real deployed requests, isolated session, no business key writes."""
import json
from pathlib import Path
import time
from demo_client import DemoClient

ROOT = Path(__file__).resolve().parent
EXPECTED_CHECKS = {
    'pq-parameter-downgrade': [f'{v}-{kind}' for v in (512, 768, 1024) for kind in ('roundtrip', 'interop', 'tamper')],
    'pq-secret-upload': [f'{v}-{kind}' for v in (512, 768, 1024) for kind in ('roundtrip', 'other-control', 'wrong-key')],
    'pq-sign-encrypt-confusion': ['falcon-roundtrip', 'falcon-interop', 'falcon-message-tamper'],
    'pq-issuance-source-forgery': ['falcon-roundtrip', 'falcon-interop', 'falcon-signature-tamper', 'falcon-other-control', 'falcon-wrong-key'],
}


def verify():
    expected_codes = json.loads((ROOT / 'expected-codes.json').read_text())
    client = DemoClient()
    results = []
    try:
        client.context('/demo-api/lifecycle/demo/context')
        client.context('/demo-api/lifecycle/demo/context/entry', {'nodeId': 'A'})
        status, body = client.request('POST', '/demo-api/pqkds/node-self/acceptance/pq/', {'caseId': 'pq-secret-upload', 'secretKey': 'dummy'})
        assert status == 400 and body['code'] == 400, 'must reject arbitrary materials'
        client.context('/demo-api/lifecycle/demo/context/admin', {})
        status, body = client.request('POST', '/demo-api/pqkds/node-self/acceptance/pq/', {'caseId': 'pq-secret-upload'})
        assert status == 403, 'admin must not bypass node scope'
        for case_id, expected in expected_codes.items():
            status, result = client.request('POST', '/acceptance-api/security/runs', {'caseId': case_id})
            assert status == 202 and result.get('id'), case_id
            deadline = time.monotonic() + 60
            while result['status'] in ('preparing', 'running', 'queued', 'cancelling'):
                assert time.monotonic() < deadline, case_id
                time.sleep(0.25)
                status, result = client.request('GET', '/acceptance-api/security/runs/' + result['id'])
                assert status == 200
            safe = {key: result.get(key) for key in (
                'id', 'caseId', 'status', 'verdict', 'passed', 'summary', 'error', 'evidenceVersion',
                'expectedCode', 'actualCode', 'expectedReason', 'actualReason', 'reasonMatched',
                'protocolPassed', 'legalControlPassed', 'algorithmEvidence', 'requests')}
            results.append(safe)
            assert result['status'] == 'completed' and result['passed'] is True and result['legalControlPassed'] is True, safe
            assert result['expectedCode'] == result['actualCode'] == expected, case_id
            assert result['reasonMatched'] is True and result['actualReason'] == result['expectedReason'], case_id
            if case_id in EXPECTED_CHECKS:
                assert result['evidenceVersion'] == 3 and result['protocolPassed'] is True, case_id
                ev = result['algorithmEvidence']
                assert ev['version'] == 1 and ev['caseId'] == case_id and ev['passed'] is True
                assert [c['id'] for c in ev['checks']] == EXPECTED_CHECKS[case_id]
                assert all(c['passed'] and c['status'] == 'passed' and c['recordedAt'] and c['expected'] and c['actual'] for c in ev['checks'])
                assert len(result['requests']) == 7
            else:
                assert result['evidenceVersion'] == 2 and len(result['requests']) == 5
        assert len(results) == len({r['actualCode'] for r in results}) == 14
        total = sum(len((r.get('algorithmEvidence') or {}).get('checks', [])) for r in results)
        assert total == 26
        report = {'allPassed': True, 'protocolCases': 14, 'uniqueActualCodes': 14, 'algorithmChecks': total,
                  'algorithmClasses': 4, 'serverNativeOnly': True, 'quantumAttackOrFIPSCertification': False,
                  'materialInputRejected': True, 'adminScopeRejected': True, 'results': results}
        (ROOT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k != 'results'}))
    finally:
        client.request('POST', '/demo-api/lifecycle/demo/context/logout', {})


if __name__ == '__main__':
    verify()
