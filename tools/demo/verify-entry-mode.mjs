import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, resolve } from 'node:path'
import test from 'node:test'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const entryURL = pathToFileURL(resolve(root, 'kms-updatedel/front/src/utils/entry-mode.js')).href
let sequence = 0
async function mode(pathname) {
  globalThis.location = { pathname, replace() {} }
  return import(`${entryURL}?case=${++sequence}`)
}

test('only the Demo application entry selects its immutable namespace', async () => {
  for (const path of ['/updatedel/login', '/updatedel/standalone', '/updatedel/foo/demo', '/updatedel/demonstration']) {
    const entry = await mode(path)
    assert.equal(entry.IS_DEMO, false, path)
    assert.equal(entry.KEYSTORE_DB_NAME, 'kms-node-keystore')
  }
  for (const path of ['/updatedel/demo', '/updatedel/demo/node/initialize', '/demo']) {
    const entry = await mode(path)
    assert.equal(entry.IS_DEMO, true, path)
    assert.equal(entry.KEYSTORE_DB_NAME, 'kms-demo-node-keystore')
    globalThis.location.pathname = '/updatedel/standalone'
    assert.equal(entry.IS_DEMO, true, 'location changes cannot retarget pending IDB work')
  }
})

test('Demo route prefixes and names are centralized without mutating sys_menu', async () => {
  const entry = await mode('/updatedel/demo')
  const component = () => null
  const routes = [{ path: '/', name: 'WorkbenchRoot', component, children: [{
    path: 'workbench', name: 'Workbench', meta: { activeMenu: '/workbench' }
  }] }, { path: '/distzone', name: 'Distribution', redirect: '/distzone/keys', children: [{ path: 'keys', name: 'Keys' }] }]
  const namespaced = entry.namespaceRoutes(routes, 'NODE')
  assert.equal(namespaced[0].path, '/demo/node')
  assert.equal(namespaced[0].children[0].path, 'workbench')
  assert.equal(namespaced[0].children[0].name, 'DemoNODE_Workbench')
  assert.equal(namespaced[0].children[0].meta.activeMenu, '/demo/node/workbench')
  assert.equal(namespaced[0].component, component)
  assert.equal(namespaced[1].redirect, '/demo/node/distzone/keys')
  assert.equal(routes[0].path, '/')
  assert.equal(routes[0].children[0].name, 'Workbench')
  entry.setEntryPrincipal('ADMIN')
  assert.equal(entry.entryPath('/nodes/index'), '/demo/admin/nodes/index')
  assert.equal(entry.entryPath('/node-init'), '/demo/node/initialize')
  assert.equal(entry.originalPath('/demo/admin/nodes/index'), '/nodes/index')
  assert.equal(entry.documentURL('/demo?nodeId=A'), '/updatedel/demo?nodeId=A')
})

test('Standalone keeps original paths and menu object identity', async () => {
  const entry = await mode('/updatedel/login')
  const routes = [{ path: '/nodes' }]
  assert.equal(entry.namespaceRoutes(routes, 'ADMIN'), routes)
  assert.equal(entry.entryPath('/node-init'), '/node-init')
  assert.equal(entry.entryPath('/workbench', 'NODE'), '/workbench')
})

async function demoModule(body, post = async () => ({ data: body })) {
  const entry = await mode('/updatedel/demo')
  const authority = { get: async () => ({ data: body }), post }
  globalThis.__kmsDemoAxios = { create: () => authority }
  let source = await readFile(resolve(root, 'kms-updatedel/front/src/utils/demo-context.js'), 'utf8')
  source = source.replace("import axios from 'axios'", 'const axios = globalThis.__kmsDemoAxios')
  source = source.replace("from './entry-mode'", `from '${entryURL}?case=${sequence}'`)
  return { entry, api: await import(`data:text/javascript;base64,${Buffer.from(`${source}\n// ${sequence}`).toString('base64')}`) }
}
const contextBody = (principalType = 'NODE', revision = 4) => ({ code: 200, data: {
  entryMode: 'DEMO', enabled: true, principalType, nodeId: principalType === 'NODE' ? 'A' : null,
  csrfToken: 'csrf-token', revision, node: { nodeId: 'A', status: 'PENDING_INIT' }
} })

test('Demo business dispatch requires server context and strips every Authorization casing', async () => {
  const { api } = await demoModule(contextBody())
  assert.throws(() => api.applyDemoRequest({ headers: {}, url: '/getInfo' }), /尚未就绪/)
  await api.loadDemoContext()
  const config = api.applyDemoRequest({ baseURL: '/generate-api', url: '/generate/key/list',
    headers: { Authorization: 'old', AUTHORIZATION: 'old2', authorization: 'old3' } })
  assert.equal(config.baseURL, '/demo-api/generate')
  assert.deepEqual(Object.keys(config.headers).sort(), ['X-Kms-Demo-CSRF','X-Kms-Demo-Revision'])
  assert.equal(config.headers['X-Kms-Demo-Revision'], '4')
  assert.equal(config.withCredentials, true)
  for (const url of ['https://other.example/api', '//other.example/api', 'data:text/plain,private']) {
    assert.throws(() => api.applyDemoRequest({ headers: {}, url }), /当前受控网关/)
  }
})

test('anonymous, disabled and unknown authority roles fail closed', async () => {
  for (const body of [contextBody(null), { ...contextBody(), data: { ...contextBody().data, enabled: false } }, contextBody('DEMO_ADMIN')]) {
    const { api } = await demoModule(body)
    if (body.data.principalType === null) {
      await api.loadDemoContext()
      assert.throws(() => api.demoHeaders(), /尚未就绪/)
    } else await assert.rejects(api.loadDemoContext(), /演示会话不可用/)
  }
})

test('role boundary aborts old requests and refuses new dispatch before full reload', async () => {
  let finish, mutation
  const { api } = await demoModule(contextBody(), (path, body, config) => {
    mutation = { path, body, config }
    return new Promise(resolve => { finish = resolve })
  })
  await api.loadDemoContext()
  const old = api.applyDemoRequest({ url: '/admin/action', headers: {} })
  const redirects = []
  globalThis.location.replace = value => redirects.push(value)
  const switching = api.switchDemo('ADMIN')
  assert.equal(old.signal.aborted, true)
  assert.throws(() => api.demoHeaders(), /正在切换/)
  assert.equal(mutation.path, '/admin')
  assert.equal(mutation.config.headers['X-Kms-Demo-Revision'], '4')
  finish({ data: contextBody('ADMIN', 5) })
  await switching
  assert.deepEqual(redirects, ['/updatedel/demo/admin/index'])
  assert.equal(old.headers['X-Kms-Demo-Revision'], '4', 'old dispatch is never upgraded to new role')
})

test('failed first entry refreshes anonymous cookie revision and can explicitly enter admin', async () => {
  const current = contextBody(null, 0)
  let first = true
  const { api } = await demoModule(current, async (path, body, config) => {
    if (first) {
      first = false
      assert.equal(path, '/entry')
      current.data = { ...current.data, csrfToken: 'issued-cookie-csrf', revision: 1 }
      return { data: { code: 403, msg: 'DEMO_NODE_NOT_FOUND', data: current.data } }
    }
    assert.equal(path, '/admin')
    assert.equal(config.headers['X-Kms-Demo-CSRF'], 'issued-cookie-csrf')
    assert.equal(config.headers['X-Kms-Demo-Revision'], '1')
    return { data: contextBody('ADMIN', 2) }
  })
  await api.loadDemoContext()
  await assert.rejects(api.enterDemo('Unknown'), /DEMO_NODE_NOT_FOUND/)
  assert.equal(api.getDemoContext().principalType, null)
  assert.equal(api.getDemoContext().revision, 1)
  assert.throws(() => api.demoHeaders(), /尚未就绪/)
  const redirects = []
  globalThis.location.replace = url => redirects.push(url)
  await api.switchDemo('ADMIN')
  assert.deepEqual(redirects, ['/updatedel/demo/admin/index'])
})
