import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
const source = readFileSync(new URL('../src/utils/demo-context.js', import.meta.url), 'utf8')
const accept = vm.runInNewContext(`let context; const setEntryPrincipal=()=>{};
  ${source.slice(source.indexOf('function acceptContext'), source.indexOf('export function loadDemoContext'))}; acceptContext`)
const data = { entryMode: 'DEMO', enabled: true, revision: 2, csrfToken: 'test' }
assert.equal(accept({ code: 200, data }).principalType, null)
assert.equal(accept({ code: 200, data: { ...data, principalType: null } }).principalType, null)
for (const principalType of ['NODE', 'ADMIN']) {
  assert.equal(accept({ code: 200, data: { ...data, principalType } }).principalType, principalType)
}
for (const bad of [{ nodeId: 'node-without-role' }, { node: {} }, { principalType: 'unknown' }, { enabled: false }]) {
  assert.throws(() => accept({ code: 200, msg: '操作成功', data: { ...data, ...bad } }), /格式无效/)
}
assert.throws(() => accept({ code: 403, msg: 'DEMO_GATEWAY_REJECTED', data }), /DEMO_GATEWAY_REJECTED/)
console.log('PASS: 匿名身份空值/省略兼容、节点身份不可省略、未知角色/关闭/错误响应拒绝')
