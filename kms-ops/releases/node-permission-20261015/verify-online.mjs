import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import https from 'node:https'
const dist = new URL('../../../kms-updatedel/front/dist/', import.meta.url)
const digest = bytes => createHash('sha256').update(bytes).digest('hex')
function get(path) {
  return new Promise((resolve, reject) => {
    const request = https.get('https://10.112.125.22:8443' + path, { rejectUnauthorized: false }, response => {
      const chunks = []
      response.on('data', chunk => chunks.push(chunk))
      response.on('end', () => resolve({ status: response.statusCode, bytes: Buffer.concat(chunks) }))
      response.on('error', reject)
    })
    request.setTimeout(15000, () => request.destroy(Error('HTTPS timeout')))
    request.on('error', reject)
  })
}
const html = readFileSync(new URL('index.html', dist))
const entry = await get('/updatedel/demo')
assert.equal(entry.status, 200)
assert.equal(digest(entry.bytes), digest(html))
const js = readdirSync(new URL('assets/', dist)).filter(name => name.endsWith('.js'))
const nodes = js.find(name => readFileSync(new URL('assets/' + name, dist)).includes(Buffer.from('请选择有效的权限等级')))
const distribution = js.find(name => readFileSync(new URL('assets/' + name, dist)).includes(Buffer.from('节点管理 → 编辑 → 权限等级')))
assert(nodes && distribution)
for (const name of [nodes, distribution]) {
  const bytes = readFileSync(new URL('assets/' + name, dist))
  const served = await get('/updatedel/assets/' + name)
  assert.equal(served.status, 200)
  assert.equal(digest(served.bytes), digest(bytes))
}
const nodesJs = readFileSync(new URL('assets/' + nodes, dist), 'utf8')
for (const value of ['权限等级', 'L1（仅查询）', 'L2（查询、生成、分发）', 'L3（查询、生成、分发、更新、回收）']) assert(nodesJs.includes(value))
assert(readFileSync(new URL('assets/' + distribution, dist), 'utf8').includes('NODE_CAPABILITY_REQUIRED'))
// Read-only unauthenticated checks, never submit a distribution or change a node.
const backend = await get('/demo-api/pqkds/node-self/')
assert.equal(backend.status, 401)
assert(backend.bytes.toString().includes('DEMO_CONTEXT_STALE'))
console.log('PASS: live HTTPS entry, node-level controls and distribution error chunks match; backend authentication healthy')
