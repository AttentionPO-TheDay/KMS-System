"""Disposable Chrome UI checks. Fixture mode never contacts the production APIs."""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
GROUPS = {
    'generation-attacks': ['generation-identity-injection', 'generation-unknown-algorithm', 'generation-malformed-json', 'generation-invalid-version'],
    'quantum-attacks': ['pq-parameter-downgrade', 'pq-sign-encrypt-confusion', 'pq-secret-upload', 'pq-issuance-source-forgery'],
    'network-attacks': ['network-session-forgery', 'network-csrf', 'network-stale-revision', 'network-role-isolation', 'network-origin', 'network-missing-session'],
}
TITLES = ['密钥生成协议校验', '抗量子生成协议安全', '无密码会话与网络边界']
STAMP = '2026-10-19T20:00:00+08:00'


def passed(case_id):
    code = 'KEYGEN_SCHEME_INVALID' if case_id == 'generation-unknown-algorithm' else 'KEYGEN_ISSUANCE_CONFLICT' if case_id == 'pq-issuance-source-forgery' else 'INVALID_PARAMETER'
    return dict(id='run-ui-' + case_id, caseId=case_id, status='completed', verdict='blocked', passed=True,
                startedAt=STAMP, finishedAt=STAMP, expectedCode=code, actualCode=code, legalControlPassed=True,
                summary='UI回归样本：非法请求明确拒绝，合法读取正常', requests=[dict(method='POST', url='/fixture', statusCode=409, message='errorCode=' + code)])


def fixture_check(browser):
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    security = [passed('generation-identity-injection')]
    polling = {'case': None, 'count': 0}
    criteria = [dict(id=key, kind='security-suite', title=title, category='security', requirement='UI回归样本',
                     target=target, operator='>=', unit='类', caseIds=ids, evidenceSource='隔离UI回归')
                for (key, ids), title, target in zip(GROUPS.items(), TITLES, [3, 3, 5])]
    scenarios = []
    perf_runs = []
    for criterion, scenario, target, actual, state in [
        ('certless-generation', 'generate-tps', 100000, 120001, 'passed'),
        ('key-update', 'update-tps', 5000, 1000, 'failed'),
        ('abnormal-revoke', 'revoke-tps', 5000, None, 'failed'),
    ]:
        criteria.append(dict(id=criterion, scenarioId=scenario, kind='scenario', title=scenario,
                             requirement='UI回归样本', target=target, operator='>' if scenario == 'generate-tps' else '>=', unit='TPS'))
        scenarios.append(dict(id=scenario, name=scenario, available=True))
        perf_runs.append(dict(id='run-ui-' + scenario, scenarioId=scenario, status=state, passedTps=state == 'passed',
                              targetTps=target, startedAt=STAMP, finishedAt=STAMP,
                              error='UI回归样本：验收密钥池不可用' if actual is None else '',
                              summary=dict(totalRequests=100 if actual is not None else 0, successfulRequestsPerSec=actual or 0,
                                           requestsPerSec=200000, successRate=100, rawOutput='UI fixture only')))

    def route(request):
        nonlocal security
        path = urlparse(request.request.url).path
        if path.endswith('/demo/context'):
            body = dict(code=200, data=dict(enabled=True, entryMode='DEMO', principalType='ADMIN', revision=1, csrfToken='ui-fixture'))
        elif path.endswith('/health'):
            body = dict(securityExecutionAvailable=True)
        elif path.endswith('/scenarios'):
            body = dict(data=scenarios)
        elif path.endswith('/acceptance/criteria'):
            body = dict(data=criteria)
        elif path.endswith('/security/runs') and request.request.method == 'POST':
            case_id = request.request.post_data_json['caseId']
            body = dict(id='run-ui-polling', caseId=case_id, status='preparing', passed=False, startedAt=STAMP)
            polling.update(case=case_id, count=0)
            security = [body] + [x for x in security if x['caseId'] != case_id]
            request.fulfill(status=202, json=body)
            return
        elif path.endswith('/security/runs'):
            if polling['case']:
                polling['count'] += 1
                if polling['count'] >= 3:
                    result = passed(polling['case']); result['id'] = 'run-ui-polling'
                    security = [result] + [x for x in security if x['caseId'] != polling['case']]
                    polling['case'] = None
            body = dict(data=security)
        elif path.endswith('/runs'):
            body = dict(data=perf_runs)
        else:
            body = dict(data=[])
        request.fulfill(json=body)

    page.route('**/demo-api/**', route)
    page.route('**/acceptance-api/**', route)
    page.goto('http://127.0.0.1:4176/acceptance/#/load-test')
    generation = page.locator('[data-criterion-id="generation-attacks"]')
    expect(generation.locator('.item-status')).to_have_text('已防御 1/4 项')
    expect(generation.locator('.security-result')).to_contain_text('防御成功')
    expect(generation.locator('.security-result')).to_contain_text('INVALID_PARAMETER')
    expect(page.locator('[data-criterion-id="certless-generation"] .performance-result')).to_contain_text('120,001 TPS')
    expect(page.locator('[data-criterion-id="key-update"] .performance-result')).to_contain_text('未达到指标')
    expect(page.locator('[data-criterion-id="abnormal-revoke"] .performance-result')).to_contain_text('尚无有效测量')
    generation.screenshot(path=str(ROOT / 'ui-fixture-partial.png'))
    page.screenshot(path=str(ROOT / 'layout-partial-desktop.png'), full_page=True)
    assert '已配置' not in page.locator('body').inner_text()
    assert '验收下限' not in page.locator('body').inner_text()
    security = [passed(case_id) for ids in GROUPS.values() for case_id in ids]
    page.get_by_role('button', name='刷新看板', exact=True).click()
    for key, ids in GROUPS.items():
        card = page.locator(f'[data-criterion-id="{key}"]')
        expect(card.locator('.item-status')).to_have_text('全部防御成功')
        expect(card.locator('.security-result')).to_have_count(len(ids))
    expect(generation.locator('.evidence-details').first).to_contain_text('HTTP 409')
    generation.screenshot(path=str(ROOT / 'ui-fixture-complete.png'))
    page.screenshot(path=str(ROOT / 'layout-complete-desktop.png'), full_page=True)
    security[0] = dict(passed(security[0]['caseId']), status='error', passed=False, error='测试节点无法进入')
    page.get_by_role('button', name='刷新看板', exact=True).click()
    expect(generation.locator('.item-status')).to_have_text('有测试未完成')
    expect(generation.locator('.security-result').first).to_contain_text('测试节点无法进入')
    security[0] = dict(passed(security[0]['caseId']), verdict='vulnerable', passed=False, actualCode='UNEXPECTED')
    page.get_by_role('button', name='刷新看板', exact=True).click()
    expect(generation.locator('.item-status')).to_have_text('存在未通过项')
    generation.locator('select').select_option('generation-invalid-version')
    generation.get_by_role('button', name='执行所选测试', exact=True).click()
    expect(generation.locator('.item-status')).to_have_text('执行中')
    expect(generation.locator('[data-case-id="generation-invalid-version"] .result-heading strong')).to_have_text('防御成功', timeout=15000)
    page.set_viewport_size({'width': 1024, 'height': 1100})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(ROOT / 'layout-1024.png'), full_page=True)
    page.close()
    return {'fixtureChecks': ['partial-success', 'complete-evidence', 'unavailable', 'defense-failure', 'async-preparing', 'performance-pass-fail-missing']}


def live_check(browser):
    origin = 'https://10.112.125.22:8443'
    context = browser.new_context(base_url=origin, viewport={'width': 1440, 'height': 1100})
    page = context.new_page()
    page.goto(origin + '/acceptance/')

    def request(method, path, data=None, headers=None):
        # Browser fetch uses Chrome's old-origin resolver mapping and TLS trust.
        return page.evaluate('''async ({method, path, data, headers}) => {
            const response = await fetch(path, {method, body: data, headers, credentials: 'same-origin'});
            return {status: response.status, body: await response.json()};
        }''', {'method': method, 'path': path, 'data': data, 'headers': headers or {}})

    response = request('GET', '/demo-api/lifecycle/demo/context')
    assert response['status'] == 200
    data = response['body']['data']
    response = request('POST', '/demo-api/lifecycle/demo/context/admin', data='{}', headers={
        'Origin': origin, 'Content-Type': 'application/json', 'X-Kms-Demo-CSRF': data['csrfToken'], 'X-Kms-Demo-Revision': str(data['revision'])})
    assert response['status'] == 200
    data = response['body']['data']
    assert data['principalType'] == 'ADMIN'
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)[:300]))
    page.goto(origin + '/acceptance/#/load-test')
    page.reload(wait_until='networkidle')
    page.screenshot(path=str(ROOT / 'live-initial.png'), full_page=True)
    for key, ids in GROUPS.items():
        card = page.locator(f'[data-criterion-id="{key}"]')
        expect(card.locator('select option')).to_have_count(len(ids) + 1)
        card.locator('select').select_option('')
        card.get_by_role('button', name=f'执行全部 {len(ids)} 项测试', exact=True).click()
        expect(card.locator('.item-status')).to_have_text('协议通过，算法待验' if key == 'quantum-attacks' else '全部防御成功', timeout=150000)
        expect(card.locator('.security-result')).to_have_count(len(ids))
        for result in card.locator('.security-result').all():
            expect(result.locator('.result-heading strong')).to_have_text('协议校验通过' if key == 'quantum-attacks' else '防御成功')
            expect(result.locator('.codes')).to_contain_text('通过')
            expect(result.locator('.evidence-details')).to_be_visible()
            expect(result.locator('.evidence-details')).to_have_attribute('open', '')
            expect(result.locator('.evidence-details li')).to_have_count(5)
            expect(result.locator('.evidence-details')).to_contain_text('攻击前验证合法节点读取')
            expect(result.locator('.evidence-details')).to_contain_text('攻击后复查合法节点读取')
            expect(result.locator('.evidence-details')).to_contain_text('耗时')
        card.screenshot(path=str(ROOT / (key + '-live.png')))
        card.locator('.case-result').first.screenshot(path=str(ROOT / (key + '-first-case-live.png')))
    page.screenshot(path=str(ROOT / 'workbench-live.png'), full_page=True)
    revision = str(data['revision'])
    response = request('GET', '/acceptance-api/security/runs', headers={'X-Kms-Demo-Revision': revision})
    results = response['body']['data']
    assert len(results) == 14 and all(x['passed'] and x['legalControlPassed'] and x['expectedCode'] == x['actualCode'] for x in results)
    assert len({x['actualCode'] for x in results}) == 14
    assert all(x['evidenceVersion'] == 2 and x['reasonMatched'] and x['expectedReason'] == x['actualReason'] for x in results)
    safe_results = [{k: item.get(k) for k in ['id', 'caseId', 'status', 'passed', 'expectedCode', 'actualCode', 'legalControlPassed', 'startedAt', 'finishedAt', 'summary', 'testInput', 'validationRule', 'actualReason', 'expectedReason', 'reasonMatched']} for item in results]
    (ROOT / 'live-ui-results.json').write_text(json.dumps({'allPassed': True, 'count': len(results), 'pageErrors': errors, 'results': safe_results}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert not errors
    request('POST', '/demo-api/lifecycle/demo/context/logout', data='{}', headers={
        'Origin': origin, 'Content-Type': 'application/json', 'X-Kms-Demo-CSRF': data['csrfToken'], 'X-Kms-Demo-Revision': revision})
    context.close()
    return {'liveUiPassed': 14, 'pageErrors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--live', action='store_true'); args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True,
            args=['--no-proxy-server', '--host-resolver-rules=MAP 10.112.125.22 10.129.114.144'])
        try:
            print(json.dumps(live_check(browser) if args.live else fixture_check(browser)))
        finally:
            browser.close()
