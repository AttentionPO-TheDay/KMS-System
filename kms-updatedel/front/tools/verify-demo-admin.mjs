import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import test from 'node:test'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const root = fileURLToPath(new URL('../', import.meta.url))
const read = path => readFileSync(resolve(root, path), 'utf8')
const entrySource = read('src/utils/entry-mode.js')
function entry() {
  const source = entrySource.replaceAll('export ', '').replaceAll('import.meta.env', '({ BASE_URL: "/updatedel/" })')
  return vm.runInNewContext(`${source}; ({ IS_DEMO, ENTRY_MODE, KEYSTORE_DB_NAME, entryPath, namespaceRoutes })`)
}

test('all documents use existing Demo namespace, never legacy private material', () => {
  const mode = entry()
  assert.equal(mode.IS_DEMO, true)
  assert.equal(mode.ENTRY_MODE, 'DEMO')
  assert.equal(mode.KEYSTORE_DB_NAME, 'kms-demo-node-keystore')
  assert.equal(mode.entryPath('/index', 'ADMIN'), '/demo/admin/index')
  assert.equal(mode.entryPath('/workbench', 'NODE'), '/demo/node/workbench')
  assert.equal(mode.entryPath('/node-init', 'NODE'), '/demo/node/initialize')
  assert.equal(mode.entryPath('/login'), '/demo')
  const namespaced = mode.namespaceRoutes([{ path: '/acceptance', name: 'Acceptance', children: [{ path: 'view' }] }], 'ADMIN')
  assert.equal(namespaced[0].path, '/demo/admin/acceptance')
  assert.equal(namespaced[0].name, 'DemoADMIN_Acceptance')
  assert.equal(namespaced[0].children[0].path, 'view')
})

test('retired links cannot load normal login or ordinary token guard', async () => {
  const mode = entry()
  const user = { roles: ['demo'], clearSession() {}, getInfo: async () => {} }
  let guard
  const source = read('src/permission.js').replace(/^import .*\n/gm, '')
  vm.runInNewContext(source, {
    router: { beforeEach(fn) { guard = fn }, afterEach() {}, addRoute() {} },
    NProgress: { configure() {}, start() {}, done() {} },
    isHttp: () => false, useUserStore: () => user,
    usePermissionStore: () => ({ routesLoaded: true }), useSettingsStore: () => ({ setTitle() {} }),
    loadDemoContext: async () => ({ principalType: 'ADMIN' }),
    entryPath: mode.entryPath, originalPath: path => path.replace(/^\/demo\/(?:node|admin)/, '') || '/',
    landingPath: () => '/demo/admin/index'
  })
  for (const path of ['/login', '/standalone', '/standalone/admin/login', '/standalone/node/login', '/index']) {
    let destination
    await guard({ path }, {}, value => { destination = value })
    assert.equal(destination.path, '/demo', path)
  }
  let redirected
  await guard({ path: '/demo/node/workbench', query: {}, hash: '' }, {}, value => { redirected = value })
  assert.equal(redirected.path, '/demo/admin/workbench', 'URL does not switch authority role')
  assert(!source.includes('getToken'))
  assert(!read('src/router/index.js').includes("import('@/views/login.vue')"))
  assert(!read('src/router/index.js').includes("import('@/views/entry/standalone.vue')"))
  assert(!read('src/views/entry/demo.vue').includes('href="/updatedel/standalone"'))
})

test('admin home is aggregate-only and summary errors clear stale values', () => {
  const home = read('src/views/index.vue')
  assert(home.includes('SecurityMonitor'))
  assert(home.includes("principalType === 'ADMIN'"))
  assert(!home.includes('lifecycle'))
  const summary = read('src/views/securityMonitor/index.vue')
  // Demo admin now exposes the canonical long-term-key states.  The former
  // `frozen`/`rotating` labels belonged to the retired user-key dashboard and
  // must not be used as an acceptance contract.
  for (const field of ['keys.total', 'keys.active', 'keys.pending', 'keys.retired', 'keys.revoked', 'keys.expired', 'byType']) assert(summary.includes(field), field)
  assert(summary.includes("return '不可用'"))
  assert(summary.includes('data.value = {}'))
  assert(summary.includes("http.get('/security-monitor/summary/',"))
  assert(!summary.includes('echarts'))
  const nodes = read('src/views/nodes/index.vue')
  assert(/<el-button v-if="!IS_DEMO"[^>]+@click="openKeys\(scope\.row\)">密钥<\/el-button>/.test(nodes))
  assert(/async function openKeys\(row\) \{\s+if \(IS_DEMO\) return/.test(nodes))
})

test('modified Vue SFCs compile using the production compiler', () => {
  for (const filename of ['src/views/index.vue', 'src/views/securityMonitor/index.vue', 'src/views/entry/demo.vue', 'src/views/nodes/index.vue']) {
    const { descriptor, errors } = parse(read(filename), { filename })
    assert.equal(errors.length, 0, filename)
    const script = compileScript(descriptor, { id: filename })
    const template = compileTemplate({ source: descriptor.template.content, filename, id: filename,
      compilerOptions: { bindingMetadata: script.bindings } })
    assert.equal(template.errors.length, 0, `${filename}: ${template.errors.join(', ')}`)
  }
})
