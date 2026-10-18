// Read-only verification of the published entry and operation-linked modules.
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import https from 'node:https'
const dist = new URL('../../../kms-updatedel/front/dist/', import.meta.url)
const host = 'https://10.112.125.22:8443'
const digest = bytes => createHash('sha256').update(bytes).digest('hex')
function get(path) {
  return new Promise((resolve, reject) => {
    // Existing deployment uses a self-signed HTTPS certificate on this IP.
    const req = https.get(host + path, { rejectUnauthorized: false }, res => {
      const parts = []
      res.on('data', part => parts.push(part))
      res.on('end', () => resolve({ status: res.statusCode, bytes: Buffer.concat(parts), headers: res.headers }))
      res.on('error', reject)
    })
    req.setTimeout(15000, () => req.destroy(Error('request timeout')))
    req.on('error', reject)
  })
}
const markers = ['业务执行流程', '本次入池回执已汇总', '本地载荷、批次与接收方已绑定', '重新读取平台与本机材料并对账']
const modules = readdirSync(new URL('assets/', dist)).filter(name => name.endsWith('.js'))
  .map(name => ({ name, bytes: readFileSync(new URL('assets/' + name, dist)) }))
const selected = markers.map(marker => {
  const found = modules.find(item => item.bytes.includes(Buffer.from(marker)))
  assert(found, `missing operation module: ${marker}`)
  return found
})
const html = readFileSync(new URL('index.html', dist))
const entry = html.toString().match(/<script[^>]+src="\/updatedel\/assets\/([^"?]+)"/)
assert(entry, 'missing entry script')
selected.push(modules.find(item => item.name === entry[1]))
for (const path of ['/updatedel/', '/updatedel/demo']) {
  const response = await get(path)
  assert.equal(response.status, 200, path)
  assert.equal(digest(response.bytes), digest(html), path)
  console.log(`PASS ${path} HTTP 200 entry_sha256=${digest(response.bytes)}`)
}
for (const item of new Set(selected)) {
  assert(item)
  const path = '/updatedel/assets/' + item.name
  const response = await get(path)
  assert.equal(response.status, 200, path)
  assert.match(response.headers['content-type'], /javascript/, path)
  assert.equal(digest(response.bytes), digest(item.bytes), path)
  console.log(`PASS ${path} HTTP 200 sha256=${digest(response.bytes)}`)
}
console.log('PASS: published entry and all three linked-operation pages match the verified local build')
