import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const api = readFileSync(new URL('../src/api/nodes/nodes.js', import.meta.url), 'utf8')
const code = api.slice(api.indexOf('export async function listAllNodes'), api.indexOf('\n/**\n * 注册'))
let responses = [], requests = []
const list = vm.runInNewContext(`${code.replace('export ', '')}; listAllNodes`, {
  http: { get: async (_url, request) => { requests.push(request.params.page); return responses.shift() } },
  unwrap: response => response?.data ?? response
})
responses = [{ total: 2, is_next: true, data: [{ id: 1 }] }, { total: 2, is_next: false, data: [{ id: 2 }] }]
assert.equal((await list()).length, 2)
assert.deepEqual(requests, [1, 2])
responses = [{ results: [{ id: 1 }], count: 2, next: '/next' }, { results: [{ id: 2 }], count: 2, next: null }]
assert.equal((await list()).length, 2)
responses = [{ total: 2, is_next: true, data: [{ id: 1 }] }, { total: 2, is_next: true, data: [{ id: 1 }] }]
await assert.rejects(list(), /分页已变化/)
responses = [{ total: 2, is_next: true, data: [] }]
await assert.rejects(list(), /分页不完整/)
const java = readFileSync(new URL('../../java-backend/ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/DemoIdentity.java', import.meta.url), 'utf8')
assert(java.includes('9461L'))
const svg = readFileSync(new URL('../src/assets/icons/svg/database.svg', import.meta.url), 'utf8')
assert(svg.includes('viewBox="0 0 24 24"'))
console.log('PASS: 域管理完整分页、错误响应防误计、管理员菜单投影及预分配池图标')
