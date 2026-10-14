import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import { ref, computed } from 'vue'
import { parse } from '@vue/compiler-sfc'

const source = readFileSync(new URL('../src/views/securityMonitor/index.vue', import.meta.url), 'utf8')
function fixture() {
  const requests = []
  const { descriptor } = parse(source)
  const code = descriptor.scriptSetup.content.replace(/^import .*\n/gm, '')
  const state = vm.runInNewContext(`${code}; ({ load, loadPoolPage, data, poolPage, pagedPoolItems, loading })`, {
    ref, computed, defineProps: () => ({ section: 'pool' }), onMounted() {},
    http: { get(url, options) { return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })) } },
    unwrap: value => value, ElMessage: { error() {} }
  })
  return { state, requests }
}

test('pool uses database total and server page, not a local 200-row list', async () => {
  assert(source.includes(':total="data.pool?.total || 0"'))
  assert(source.includes('@current-change="loadPoolPage"'))
  const { state, requests } = fixture()
  const pending = state.loadPoolPage(21)
  assert.equal(requests[0].options.params.poolPage, 21)
  assert.equal(requests[0].options.params.poolPageSize, 10)
  requests[0].resolve({ pool: { total: 301, page: 21, items: [{ id: 201 }] } })
  await pending
  assert.equal(state.poolPage.value, 21)
  assert.equal(state.data.value.pool.total, 301)
  assert.equal(state.pagedPoolItems.value[0].id, 201)
  const refresh = state.load({ type: 'click' })
  assert.equal(requests[1].options.params.poolPage, 1)
  requests[1].resolve({ pool: { total: 302, page: 1, items: [] } })
  await refresh
  assert.equal(state.data.value.pool.total, 302)
})

test('late responses cannot overwrite a newer page, loading, or failure state', async () => {
  const { state, requests } = fixture()
  const old = state.loadPoolPage(21)
  const latest = state.loadPoolPage(30)
  requests[1].resolve({ pool: { total: 301, page: 30, items: [{ id: 300 }] } })
  await latest
  requests[0].resolve({ pool: { total: 200, page: 21, items: [] } })
  await old
  assert.equal(state.poolPage.value, 30)
  assert.equal(state.data.value.pool.total, 301)
  assert.equal(state.loading.value, false)
  const failure = state.loadPoolPage(31)
  requests[2].reject(new Error('offline'))
  await failure
  assert.equal(state.data.value.pool, undefined)
  assert.equal(state.poolPage.value, 1)
})
