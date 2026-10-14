import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const page = readFileSync(new URL('../src/views/preallocate/index.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/pqkds/node-self.js', import.meta.url), 'utf8')

assert(!page.includes('recordPreallocationAcceptanceEvidence'), '普通预分配不得回传验收证据')
assert(!page.includes('验收结果看板'), '普通预分配结果不得展示验收判定')
assert(!page.includes('指标 ≥ 50'), '普通预分配不得套用验收阈值')
assert(!api.includes('node-self/acceptance/preallocation-evidence'), '业务前端不得暴露验收证据写接口')

console.log('preallocation business/acceptance boundary checks passed')
