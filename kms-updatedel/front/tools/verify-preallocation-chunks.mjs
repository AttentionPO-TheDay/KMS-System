import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import { webcrypto } from 'node:crypto'

const page = readFileSync(new URL('../src/views/preallocate/index.vue', import.meta.url), 'utf8')
const submitSource = page.match(/async function submit\(\) \{[\s\S]*?\n\}/)?.[0]
assert(submitSource, 'Production submit function must be available')

async function submit(count, rejectIndex = -1) {
  const calls = [], errors = [], uploaded = [], stored = new Map()
  let prepared = 0
  const context = {
    canSubmit: { value: true }, submitting: { value: false }, result: { value: null },
    technicalFlow: { value: null }, selfNodeId: { value: 'A' },
    form: { nodeCode: 'C', count, ttlHours: 24 },
    falconKey: { value: { keyRef: 'local-falcon', keyId: 'falcon-id', keyVersion: 1 } },
    crypto: webcrypto, performance, chunkSize: 200, cryptoProvider: {},
    toHex: bytes => Buffer.from(bytes).toString('hex'),
    fetchPeerKyberKey: async () => ({ keyId: 'kyber-id', keyVersion: 1, publicKey: 'public' }),
    generatePayloadKey: () => new Uint8Array(16),
    buildNodeEnvelope: async ({ batchId }) => {
      const keyHash = String(prepared++).padStart(64, '0')
      return { envelope: { batch_id: batchId, key_hash: keyHash }, keyHash }
    },
    signNodeEnvelope: async () => 'signed',
    sealPoolSecret: async () => {},
    markPoolSecretsUploaded: async (_node, _pool, hashes) => uploaded.push(...hashes),
    preallocatePool: async payload => {
      calls.push(payload)
      assert(Number.isInteger(payload.startIndex))
      assert(payload.items.length <= 200)
      const failed = []
      payload.items.forEach((item, index) => {
        const globalIndex = payload.startIndex + index
        if (globalIndex === rejectIndex || stored.has(globalIndex)) {
          failed.push({ index, errorCode: 'REJECTED', message: 'rejected item' })
        } else {
          stored.set(globalIndex, item.keyHash)
        }
      })
      return { generated: payload.items.length - failed.length, failed, serverMs: 1 }
    },
    ElMessage: { success() {}, warning() {}, error(message) { errors.push(message) } }
  }
  await vm.runInNewContext(`(${submitSource})`, context)()
  assert.deepEqual(errors, [])
  assert.equal(context.submitting.value, false)
  return { calls, result: context.result.value, stored, uploaded }
}

test('the real submit logic keeps unique offsets across 1000 and 2000 prepared items', async () => {
  for (const count of [1000, 2000]) {
    const { calls, result, stored, uploaded } = await submit(count)
    assert.deepEqual(calls.map(x => x.startIndex), Array.from({ length: count / 200 }, (_, i) => i * 200))
    assert.equal(new Set(calls.map(x => x.poolId)).size, 1)
    assert.equal(result.generated, count)
    assert.equal(result.failed.length, 0)
    assert.equal(stored.size, count)
    assert.equal(uploaded.length, count)
    for (let i = 0; i < count; i++) assert.equal(stored.get(i), String(i).padStart(64, '0'))
  }
})

test('short final chunks and legacy-size single uploads use correct offsets', async () => {
  for (const count of [1, 100, 200, 201, 401]) {
    const { calls, result } = await submit(count)
    assert.equal(result.generated, count)
    assert.equal(calls.at(-1).items.length, (count - 1) % 200 + 1)
    assert.equal(calls.at(-1).startIndex, Math.floor((count - 1) / 200) * 200)
  }
})

test('a later chunk failure retains the global display index and excludes local upload marking', async () => {
  const { result, uploaded } = await submit(1000, 403)
  assert.equal(result.generated, 999)
  assert.equal(result.failed.length, 1)
  assert.equal(result.failed[0].index, 403)
  assert.equal(uploaded.length, 999)
  assert(!uploaded.includes(String(403).padStart(64, '0')))
})
