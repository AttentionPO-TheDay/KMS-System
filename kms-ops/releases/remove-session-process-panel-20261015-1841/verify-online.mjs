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
const name = readdirSync(new URL('assets/', dist)).find(name => name.endsWith('.js') && readFileSync(new URL('assets/' + name, dist)).includes(Buffer.from('本机处理完成，等待对方确认')))
assert(name, 'missing session page')
const bytes = readFileSync(new URL('assets/' + name, dist))
for (const removed of ['处理中止', '处理会话', '提交持有证明', '回报解封成功']) assert(!bytes.includes(Buffer.from(removed)), removed)
const served = await get('/updatedel/assets/' + name)
assert.equal(served.status, 200)
assert.equal(digest(served.bytes), digest(bytes))
console.log('PASS: HTTPS entry and session page match; removed processing panel and abort label absent; normal confirmation feedback retained')
