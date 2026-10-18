// Read-only HTTPS checks against the exact locally verified production assets.
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
for (const path of ['/updatedel/', '/updatedel/demo']) {
  const result = await get(path)
  assert.equal(result.status, 200)
  assert.equal(digest(result.bytes), digest(html))
  console.log('PASS entry ' + path)
}
const modules = readdirSync(new URL('assets/', dist)).filter(name => name.endsWith('.js'))
  .map(name => ({ name, bytes: readFileSync(new URL('assets/' + name, dist)) }))
const selected = new Set()
for (const marker of ['本机没有可取用的预分配密钥副本', '取用回执与本机预分配材料不一致', '本次入池回执已汇总', '本浏览器缺少该会话密钥']) {
  const module = modules.find(item => item.bytes.includes(Buffer.from(marker)))
  assert(module, 'Missing built repair: ' + marker)
  selected.add(module)
}
for (const module of selected) {
  const result = await get('/updatedel/assets/' + module.name)
  assert.equal(result.status, 200)
  assert.equal(digest(result.bytes), digest(module.bytes))
  console.log('PASS repair asset ' + module.name)
}
const backend = await get('/demo-api/pqkds/node-self/')
assert.equal(backend.status, 401)
assert.equal(JSON.parse(backend.bytes).data.error_code, 'DEMO_CONTEXT_STALE')
console.log('PASS running Django authentication boundary; no business records changed')
