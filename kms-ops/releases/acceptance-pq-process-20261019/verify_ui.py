"""Real Chrome at the preserved origin, disposable profile, no business key storage access."""
from copy import deepcopy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://10.112.125.22:8443'
GROUPS = {
    'generation-attacks': ['generation-identity-injection', 'generation-unknown-algorithm', 'generation-malformed-json', 'generation-invalid-version'],
    'quantum-attacks': ['pq-parameter-downgrade', 'pq-sign-encrypt-confusion', 'pq-secret-upload', 'pq-issuance-source-forgery'],
    'network-attacks': ['network-session-forgery', 'network-csrf', 'network-stale-revision', 'network-role-isolation', 'network-origin', 'network-missing-session'],
}


def verify(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 1100})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)[:300]))
    def request(method, path, data=None, auth=None):
        return page.evaluate('''async ({method,path,data,auth}) => {
            const response = await fetch(path, {method, credentials:'same-origin',
                body:data ? JSON.stringify(data) : undefined,
                headers:{'Content-Type':'application/json',...(auth || {})}});
            return {status:response.status,body:await response.json()};
        }''', {'method': method, 'path': path, 'data': data, 'auth': auth})
    auth = None
    try:
        page.goto(ORIGIN + '/acceptance/')
        bootstrap = request('GET', '/demo-api/lifecycle/demo/context')['body']['data']
        initial_auth = {'X-Kms-Demo-CSRF': bootstrap['csrfToken'], 'X-Kms-Demo-Revision': str(bootstrap['revision'])}
        admin = request('POST', '/demo-api/lifecycle/demo/context/admin', {}, initial_auth)
        assert admin['status'] == 200 and admin['body']['data']['principalType'] == 'ADMIN'
        data = admin['body']['data']
        auth = {'X-Kms-Demo-CSRF': data['csrfToken'], 'X-Kms-Demo-Revision': str(data['revision'])}
        page.goto(ORIGIN + '/acceptance/#/load-test')
        page.reload(wait_until='networkidle')
        for key, ids in GROUPS.items():
            card = page.locator(f'[data-criterion-id="{key}"]')
            expect(card.locator('select option')).to_have_count(len(ids) + 1)
            card.locator('select').select_option('')
            card.get_by_role('button', name=f'执行全部 {len(ids)} 项测试', exact=True).click()
            expect(card.locator('.item-status')).to_have_text('全部验证通过' if key == 'quantum-attacks' else '全部防御成功', timeout=90000)
            expect(card.locator('.security-result')).to_have_count(len(ids))
            for result in card.locator('.security-result').all():
                expect(result.locator('.result-heading strong')).to_have_text('算法与协议验证通过' if key == 'quantum-attacks' else '防御成功')
                expect(result.locator('.evidence-details li')).to_have_count(7 if key == 'quantum-attacks' else 5)
                expect(result.locator('.codes')).to_contain_text('通过')
                if key == 'quantum-attacks':
                    expect(result.locator('.algorithm-evidence')).to_be_visible()
                    expect(result.locator('.algorithm-evidence')).to_contain_text('预期：')
                    expect(result.locator('.algorithm-evidence')).to_contain_text('实际：')
                    assert result.locator('.algorithm-evidence .check-passed').count() in (3, 5, 9)
            if key == 'quantum-attacks':
                expect(card.locator('.algorithm-evidence li')).to_have_count(26)
                expect(card.locator('.check-failed, .check-error')).to_have_count(0)
                expect(card).to_contain_text('隐式拒绝生效')
                expect(card).to_contain_text('独立 JS')
                expect(card).to_contain_text('跨密钥隔离生效')
            card.screenshot(path=str(ROOT / (key + '-live.png')))
            card.locator('.case-result').first.screenshot(path=str(ROOT / (key + '-first-case-live.png')))
        results = request('GET', '/acceptance-api/security/runs', auth=auth)['body']['data']
        assert len(results) == 14 and len({r['actualCode'] for r in results}) == 14
        assert all(r['passed'] and r['reasonMatched'] and r['legalControlPassed'] for r in results)
        assert sum(len((r.get('algorithmEvidence') or {}).get('checks', [])) for r in results) == 26
        page.set_viewport_size({'width': 1024, 'height': 1100})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(ROOT / 'layout-1024.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1100})
        page.screenshot(path=str(ROOT / 'workbench-live.png'), full_page=True)

        # Rendering-only negative QA. These fixtures never enter production records.
        original = next(r for r in results if r['caseId'] == 'pq-parameter-downgrade')
        visible = [deepcopy(original)]
        def fixture(route):
            route.fulfill(json={'data': visible})
        page.route('**/acceptance-api/security/runs', fixture)
        card = page.locator('[data-criterion-id="quantum-attacks"]')
        visible[0]['passed'] = False
        visible[0]['verdict'] = 'vulnerable'
        visible[0]['algorithmEvidence']['passed'] = False
        failed = visible[0]['algorithmEvidence']['checks'][2]
        failed.update(passed=False, status='failed', actual='UI回归样本：篡改密文仍恢复原共享密钥')
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(card.locator('.item-status')).to_have_text('存在未通过项')
        expect(card.locator('.check-failed')).to_contain_text('失败')
        card.screenshot(path=str(ROOT / 'fixture-algorithm-failure.png'))
        visible[:] = [deepcopy(original)]
        visible[0].update(evidenceVersion=2)
        visible[0].pop('algorithmEvidence')
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(card.locator('.result-heading strong')).to_have_text('协议通过，算法待验')
        expect(card.locator('.security-result')).to_contain_text('请重新执行')
        visible[:] = [deepcopy(original)]
        visible[0].update(status='error', passed=False, verdict='insufficient_evidence', error='UI回归样本：算法执行异常')
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(card.locator('.result-heading strong')).to_have_text('测试未完成')
        page.unroute('**/acceptance-api/security/runs', fixture)
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(card.locator('.item-status')).to_have_text('全部验证通过')
        assert not errors, errors
        report = {'liveUiPassed': 14, 'algorithmChecksPassed': 26, 'uniqueRejectionCodes': 14, 'pageErrors': errors,
                  'renderingOnlyQA': ['algorithm-failure-visible', 'legacy-needs-rerun', 'execution-error-incomplete', '1024-no-overflow'],
                  'results': [{k: r.get(k) for k in ('caseId', 'status', 'passed', 'actualCode', 'evidenceVersion', 'protocolPassed', 'algorithmEvidence')} for r in results]}
        (ROOT / 'live-ui-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'results'}))
    finally:
        if auth:
            request('POST', '/demo-api/lifecycle/demo/context/logout', {}, auth)
        context.close()


if __name__ == '__main__':
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True,
            args=['--no-proxy-server', '--host-resolver-rules=MAP 10.112.125.22 10.129.114.144'])
        try:
            verify(browser)
        finally:
            browser.close()
