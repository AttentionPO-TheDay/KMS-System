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
for (const marker of ['已取用一条预分配资源', '已驳回（未授予任何权限）', '版本回执已收到，刷新对账尚未确认一致']) {
  const module = modules.find(item => item.bytes.includes(Buffer.from(marker)))
  assert(module, 'Missing repaired module: ' + marker)
  assert(!module.bytes.includes(Buffer.from('chainWarning')), 'Popup source remains: ' + module.name)
  assert(!module.bytes.includes(Buffer.from('但存证未成功（更新本身已生效')), 'Update popup source remains')
  selected.add(module)
}
const entryName = html.toString().match(/<script[^>]+src="\/updatedel\/assets\/([^"?]+)"/)[1]
selected.add(modules.find(item => item.name === entryName))
for (const module of selected) {
  assert(module)
  const result = await get('/updatedel/assets/' + module.name)
  assert.equal(result.status, 200)
  assert.equal(digest(result.bytes), digest(module.bytes))
  console.log('PASS repaired asset ' + module.name)
}
console.log('PASS: the published build matches the locally tested no-chain-warning policy')
