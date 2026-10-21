"""Check deployed copy, navigation and result rendering without submitting business writes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://10.112.125.22:8443'


def api(page, method, path, data=None, headers=None):
    return page.evaluate('''async ({method,path,data,headers}) => {
      const r=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',
        ...(headers||{})},body:data===null?undefined:JSON.stringify(data)});
      const body=await r.json(); if(!r.ok || body.code!==200) throw new Error(path+': '+JSON.stringify(body));
      return body.data;
    }''', dict(method=method,path=path,data=data,headers=headers))


def context_headers(state):
    return {'X-Kms-Demo-CSRF':state['csrfToken'],'X-Kms-Demo-Revision':str(state['revision'])}


def check_page(page, path, name, errors, report):
    response=page.goto(ORIGIN+path,wait_until='networkidle',timeout=45000)
    # Hash-router navigation stays in the loaded document and has no HTTP response.
    assert response is None or response.status==200, path
    assert page.url.startswith(ORIGIN), page.url
    page.wait_for_timeout(500)
    text=page.locator('body').inner_text()
    assert '404错误' not in text and '找不到网页' not in text, path
    assert len(text.strip())>20, path
    report[name]={'path':path,'bodyLength':len(text),'horizontalOverflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')}
    if name in ('node-workbench','acceptance','admin-summary'):
        page.screenshot(path=str(ROOT/(name+'.png')),full_page=True)
    assert not errors, errors
    return text


def main():
    report={}
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',
                                  headless=True,args=['--no-proxy-server'])
        node=browser.new_context(viewport={'width':1440,'height':1000})
        page=node.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)[:300]))
        page.goto(ORIGIN+'/updatedel/demo',wait_until='networkidle')
        initial=api(page,'GET','/demo-api/lifecycle/demo/context')
        state=api(page,'POST','/demo-api/lifecycle/demo/context/entry',{'nodeId':'A'},context_headers(initial))
        assert state['principalType']=='NODE' and state['node']['status']=='ACTIVE'
        check_page(page,'/updatedel/demo/node/workbench','node-workbench',errors,report)
        links=page.locator('a[href*="/demo/node/"]').evaluate_all('(items)=>[...new Set(items.map(a=>a.getAttribute("href")))].filter(p=>!p.includes("profile"))')
        visited=[]
        for index,path in enumerate(links):
            if index>=18:break
            text=check_page(page,path,'node-route-'+str(index),errors,report)
            visited.append(path)
        report['nodeRoutes']=visited
        # Independent administrator session; no node identity or local key material is reused.
        admin=browser.new_context(viewport={'width':1440,'height':1000})
        ap=admin.new_page()
        ap.on('pageerror',lambda error:errors.append(str(error)[:300]))
        ap.goto(ORIGIN+'/updatedel/demo',wait_until='networkidle')
        initial=api(ap,'GET','/demo-api/lifecycle/demo/context')
        state=api(ap,'POST','/demo-api/lifecycle/demo/context/admin',{},context_headers(initial))
        assert state['principalType']=='ADMIN'
        check_page(ap,'/updatedel/demo/admin/index','admin-summary',errors,report)
        admin_links=ap.locator('a[href*="/demo/admin/"]').evaluate_all('(items)=>[...new Set(items.map(a=>a.getAttribute("href")))].filter(p=>!p.includes("profile"))')
        for index,path in enumerate(admin_links[:15]):
            check_page(ap,path,'admin-route-'+str(index),errors,report)
        text=check_page(ap,'/acceptance/#/load-test','acceptance',errors,report)
        for removed in ('选择测试项目，查看执行过程与判定结果','按项目测量，保留执行阶段与测量证据',
                        '已配置 4 项','尚未达到验收下限'):
            assert removed not in text, removed
        assert '性能测试' in text and '安全测试' in text
        assert ap.locator('[data-criterion-id="quantum-attacks"]').count()==1
        details=ap.locator('details.algorithm-evidence')
        if details.count():
            first=details.first
            assert first.get_attribute('open') is None
            first.locator('summary').click()
            assert first.get_attribute('open') is not None
            first.locator('summary').click()
            assert first.get_attribute('open') is None
        report['algorithmDisclosureCount']=details.count()
        check_page(ap,'/acceptance/#/lifecycle','lifecycle',errors,report)
        report['pageErrors']=errors
        report['submittedBusinessOperations']=0
        report['passed']=True
        browser.close()
    (ROOT/'browser-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'pages':sum(isinstance(x,dict) and 'path' in x for x in report.values()),
                      'algorithmDisclosureCount':report['algorithmDisclosureCount'],'pageErrors':errors}))


if __name__=='__main__':
    main()
