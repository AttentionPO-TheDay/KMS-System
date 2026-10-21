"""Verify native disclosure behavior at the preserved HTTPS origin."""
from copy import deepcopy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://10.112.125.22:8443'

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True,
        args=['--no-proxy-server', '--host-resolver-rules=MAP 10.112.125.22 10.129.114.144'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1100})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)[:300]))
    auth = None
    def request(method, path, data=None, headers=None):
        return page.evaluate('''async ({method,path,data,headers}) => {
            const r=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',...(headers || {})},body:data===null?undefined:JSON.stringify(data)});
            return {status:r.status,body:await r.json()};
        }''', {'method': method, 'path': path, 'data': data, 'headers': headers})
    try:
        page.goto(ORIGIN + '/acceptance/')
        initial = request('GET', '/demo-api/lifecycle/demo/context')['body']['data']
        auth = {'X-Kms-Demo-CSRF': initial['csrfToken'], 'X-Kms-Demo-Revision': str(initial['revision'])}
        admin = request('POST', '/demo-api/lifecycle/demo/context/admin', {}, auth)
        assert admin['status'] == 200
        data = admin['body']['data']
        auth = {'X-Kms-Demo-CSRF': data['csrfToken'], 'X-Kms-Demo-Revision': str(data['revision'])}
        page.goto(ORIGIN + '/acceptance/#/load-test')
        page.reload(wait_until='networkidle')
        card = page.locator('[data-criterion-id="quantum-attacks"]')
        card.get_by_role('button', name='执行全部 4 项测试', exact=True).click()
        expect(card.locator('.item-status')).to_have_text('全部验证通过', timeout=90000)
        expect(card.locator('details.algorithm-evidence')).to_have_count(4)
        check_count = 0
        for item in card.locator('.security-result').all():
            details = item.locator('details.algorithm-evidence')
            summary = details.locator('summary')
            assert details.get_attribute('open') is None
            expect(item.locator('.result-heading strong')).to_be_visible()
            expect(item.locator('.result-heading strong')).to_have_text('算法与协议验证通过')
            expect(details.locator('li').first).not_to_be_visible()
            summary.click()
            expect(details).to_have_attribute('open', '')
            expect(details.locator('li').first).to_be_visible()
            check_count += details.locator('li').count()
            summary.click()
            expect(details.locator('li').first).not_to_be_visible()
        assert check_count == 26
        first = card.locator('details.algorithm-evidence').first
        first.locator('summary').focus()
        page.keyboard.press('Enter')
        expect(first.locator('li').first).to_be_visible()
        page.keyboard.press('Space')
        expect(first.locator('li').first).not_to_be_visible()
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(first.locator('li').first).not_to_be_visible()
        card.screenshot(path=str(ROOT / 'algorithm-collapsed.png'))
        first.locator('summary').click()
        card.locator('.case-result').first.screenshot(path=str(ROOT / 'algorithm-expanded.png'))
        first.locator('summary').click()
        results = request('GET', '/acceptance-api/security/runs', headers=auth)['body']['data']
        failed = deepcopy(results[0])
        failed.update(passed=False, verdict='vulnerable')
        failed['algorithmEvidence']['passed'] = False
        failed['algorithmEvidence']['checks'][0].update(passed=False, status='failed')
        page.route('**/acceptance-api/security/runs', lambda route: route.fulfill(json={'data': [failed]}))
        page.get_by_role('button', name='刷新看板', exact=True).click()
        expect(card.locator('.item-status')).to_have_text('存在未通过项')
        expect(card.locator('.result-heading strong')).to_be_visible()
        expect(card.locator('.result-heading strong')).to_have_text('防御校验未通过')
        expect(card.locator('details.algorithm-evidence li').first).not_to_be_visible()
        page.set_viewport_size({'width': 1024, 'height': 1100})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors, errors
        report = {'passed': True, 'defaultCollapsed': 4, 'algorithmChecksRetained': 26,
            'clickExpandCollapse': True, 'keyboardEnterSpace': True, 'refreshPreservesCollapse': True,
            'failureVisibleWhenCollapsed': True, 'failureRenderingOnly': True, 'pageErrors': errors}
        (ROOT / 'ui-verification.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    finally:
        if auth:
            request('POST', '/demo-api/lifecycle/demo/context/logout', {}, auth)
        context.close()
        browser.close()
