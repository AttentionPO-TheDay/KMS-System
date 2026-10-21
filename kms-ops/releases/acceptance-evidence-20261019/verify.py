#!/usr/bin/env python3
"""Run the three fixed generation probes through an isolated Demo admin session."""
import http.cookiejar
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def inspect(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]


class DemoClient:
    def __init__(self):
        gateway = inspect('kms_gateway')
        ip = next(iter(gateway['NetworkSettings']['Networks'].values()))['IPAddress']
        self.base = 'http://' + ip + ':8088'
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf, self.revision = '', ''

    def request(self, method, path, data=None):
        req = urllib.request.Request(
            self.base + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Host': '127.0.0.1:8088', 'Origin': 'http://127.0.0.1:8088',
                     'Content-Type': 'application/json', 'X-Kms-Demo-CSRF': self.csrf,
                     'X-Kms-Demo-Revision': str(self.revision)})
        try:
            response = self.client.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def context(self, path, data=None):
        status, body = self.request('GET' if data is None else 'POST', path, data)
        if status != 200 or body.get('code') != 200:
            raise RuntimeError('Demo context failed: HTTP ' + str(status))
        result = body.get('data', {})
        self.csrf = result.get('csrfToken', self.csrf)
        self.revision = result.get('revision', self.revision)
        return result


def main(case_ids=None, output_name='verification.json'):
    client = DemoClient()
    results = []
    try:
        client.context('/demo-api/lifecycle/demo/context')
        node = client.context('/demo-api/lifecycle/demo/context/entry', {'nodeId': 'A'})
        if node.get('principalType') != 'NODE':
            raise RuntimeError('A did not enter as NODE')
        status, body = client.request('GET', '/demo-api/pqkds/node-self/')
        data = body.get('data', {})
        if status != 200 or body.get('code') != 200 or data.get('mapped') is not True or data.get('node', {}).get('nodeId') != 'A':
            raise RuntimeError('A legal control failed')
        admin = client.context('/demo-api/lifecycle/demo/context/admin', {})
        if admin.get('principalType') != 'ADMIN':
            raise RuntimeError('isolated Demo admin entry failed')
        for case_id in case_ids or ['generation-identity-injection', 'generation-unknown-algorithm', 'generation-malformed-json']:
            status, run = client.request('POST', '/acceptance-api/security/runs', {'caseId': case_id})
            if status not in (200, 202) or not run.get('id'):
                raise RuntimeError('cannot start ' + case_id + ': HTTP ' + str(status))
            deadline = time.monotonic() + 75
            while run.get('status') in ('preparing', 'running', 'queued', 'cancelling') and time.monotonic() < deadline:
                time.sleep(0.5)
                status, run = client.request('GET', '/acceptance-api/security/runs/' + run['id'])
                if status != 200:
                    raise RuntimeError('cannot poll ' + case_id)
            if run.get('status') in ('preparing', 'running', 'queued', 'cancelling'):
                raise RuntimeError('probe did not finish within deadline: ' + case_id)
            # Public probe metadata only; never persist cookies, context responses or keys.
            safe = {k: run.get(k) for k in ['id', 'caseId', 'status', 'verdict', 'passed', 'summary', 'error', 'startedAt', 'finishedAt', 'expectedCode', 'actualCode', 'legalControlPassed', 'evidenceVersion', 'testInput', 'validationRule', 'expectedReason', 'actualReason', 'reasonMatched']}
            safe['requests'] = [
                {k: trace.get(k) for k in ['name', 'method', 'url', 'statusCode', 'message', 'recordedAt', 'durationMs']}
                for trace in run.get('requests', [])]
            results.append(safe)
            print(json.dumps(safe, ensure_ascii=False), flush=True)
        expected = json.loads((Path(__file__).parent / 'expected-codes.json').read_text())
        assert len(results) == len(expected) == len({r['actualCode'] for r in results}) == 14
        assert all(r['actualCode'] == expected[r['caseId']] for r in results)
        public = {'node': 'A', 'allPassed': all(r['passed'] is True and r['status'] == 'completed' and r['legalControlPassed'] is True and r['expectedCode'] == r['actualCode'] and r['evidenceVersion'] == 2 and r['reasonMatched'] is True and r['expectedReason'] == r['actualReason'] for r in results), 'results': results}
        (Path(__file__).parent / output_name).write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if not public['allPassed']:
            raise RuntimeError('one or more security probes did not pass')
    finally:
        try:
            client.request('POST', '/demo-api/lifecycle/demo/context/logout', {})
        except Exception:
            pass


if __name__ == '__main__':
    main()
