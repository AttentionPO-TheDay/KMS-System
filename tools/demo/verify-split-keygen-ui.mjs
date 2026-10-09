import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import test from 'node:test'
import { createRequire } from 'node:module'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const front = path.join(root, 'kms-updatedel/front')
const schemeURL = pathToFileURL(path.join(front, 'src/utils/crypto/generation-scheme.js')).href
const { formatGenerationName, coreDetail } = await import(schemeURL)
const generation = { schemeId: 'KMS_SPLIT_KEM_V1', schemeVersion: 1, generationIssuanceId: 'original-issuance', authorizationTicketId: 'renewable-ticket' }

async function apiFixture(demo) {
  let source = await readFile(path.join(front, 'src/api/pqkds/node-self.js'), 'utf8')
  source = source.replace("import http, { unwrap, pqkdsBaseURL } from '@/api/pqkds/http'", 'const {http,unwrap,pqkdsBaseURL}=globalThis.__splitApiFixture;')
  source = source.replace("import { IS_DEMO } from '@/utils/entry-mode'", `const IS_DEMO=${demo};`)
  source = source.replace("import { publicGeneration } from '@/utils/crypto/generation-scheme.js'", `import {publicGeneration} from '${schemeURL}';`)
  const calls = []
  const send = async (...args) => { calls.push(args); return { data: { ok: true } } }
  globalThis.__splitApiFixture = { http: { post: send, get: send }, unwrap: response => response.data, pqkdsBaseURL: '/isolated' }
  const api = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)
  return { api, calls }
}

for (const demo of [true, false]) {
  test(`${demo ? 'Demo' : 'Standalone'} issuance and renewal API allowlist public inputs and preserve lease headers`, async () => {
    const { api, calls } = await apiFixture(demo)
    const headers = { 'X-Kms-Demo-Init-Lease': 'lease' }
    await api.issueSelfNodeKeygen({ algorithm: 'KYBER', nodeId: 'never-trust-client-node', keyId: 'key', keyVersion: 2, variant: 768, deviceId: 'fingerprint', localSecret: 'never-upload' }, headers)
    assert.deepEqual(calls[0], ['/node-self/keygen/issuances/', { algorithm: 'KYBER', keyId: 'key', keyVersion: 2, variant: 768, ...(!demo ? { deviceId: 'fingerprint' } : {}) }, { headers }])
    await api.renewSelfNodeKeygenAuthorization({ generationIssuanceId: 'original-issuance', publicKey: 'ab', deviceId: 'fingerprint', share: 'never-upload', seed: 'never-upload' }, headers)
    assert.deepEqual(calls[1], ['/node-self/keygen/authorizations/', { generationIssuanceId: 'original-issuance', publicKey: 'ab', ...(!demo ? { deviceId: 'fingerprint' } : {}) }, { headers }])
    await api.registerSelfNodePublicKey('KYBER', 'ab', '768', 'fingerprint', 'key', 2, true, headers, { generation, privateKey: 'never-upload' })
    assert.deepEqual(calls[2][1].generation, generation)
    assert.equal(calls[2][1].rotate, true)
    assert.equal(calls[2][1].keyVersion, 2)
    assert.equal(calls[2][1].deviceId, demo ? undefined : 'fingerprint')
    assert.equal(calls[2][2].headers, headers)
    assert(!JSON.stringify(calls).includes('never-upload'))
    assert.throws(() => api.registerSelfNodePublicKey('KYBER', 'ab', '768', 'fingerprint', 'key', 2, false, headers,
      { generation: { ...generation, secret: 'never-upload' } }), /非公开或未知字段/)
    assert.equal(calls.length, 3, 'nested generation secrets are rejected before HTTP')
    await api.registerSelfNodePublicKey('SM2', 'ab', undefined, 'fingerprint', 'sm2', 1, undefined, headers)
    assert.equal(calls[3][1].generation, undefined, 'old positional/header callers are unchanged')
    await api.listSelfNodeKeygenIssuances('fingerprint', headers)
    assert.deepEqual(calls[4], ['/node-self/keygen/issuances/', { params: demo ? {} : { deviceId: 'fingerprint' }, headers }])
    await api.issueSelfNodeKeygen({ algorithm: 'KYBER', keyId: 'key', keyVersion: 2, variant: 768, deviceId: 'fingerprint', abandonGenerationIssuanceId: 'explicit-old-source' }, headers)
    assert.equal(calls[5][1].abandonGenerationIssuanceId, 'explicit-old-source')
  })
}

test('new and historical source labels stay distinct without changing protocol enums', () => {
  assert.equal(formatGenerationName('KYBER', generation), '改进型双份额 KEM（实验版 v1）')
  assert.equal(formatGenerationName('KYBER'), '历史兼容 KEM（来源未记录）')
  assert.equal(formatGenerationName('FALCON'), '历史兼容签名（来源未记录）')
  assert.equal(formatGenerationName('FALCON', { ...generation, schemeId: 'KMS_SPLIT_SIGN_V1' }), '改进型双份额签名（实验版 v1）')
  assert.equal(formatGenerationName('SM2'), 'SM2')
  assert.equal(formatGenerationName('SSCL'), 'SSCL')
  assert.throws(() => formatGenerationName('KYBER', 'UNKNOWN_SCHEME'), /未知生成方案/)
  assert.match(coreDetail('KYBER', 1024), /round-3 \/ 1024；不是 ML-KEM/)
  assert.match(coreDetail('FALCON'), /Falcon-512 round-3（非 padded）；不是 FN-DSA/)
})

const require = createRequire(path.join(front, 'package.json'))
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
for (const name of ['generate/create', 'keyupdate/index', 'nodeInit/index', 'generateHistory/index', 'keyVersionHistory/index', 'workbench/index']) {
  test(`${name}.vue compiles and renders source-aware labels through the shared formatter`, async () => {
    const filename = path.join(front, `src/views/${name}.vue`)
    const source = await readFile(filename, 'utf8')
    const { descriptor, errors } = parse(source, { filename })
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: name })
    const template = compileTemplate({ source: descriptor.template.content, filename, id: name, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
    assert.match(source, /formatGenerationName/)
    if (['generate/create', 'keyupdate/index', 'nodeInit/index'].includes(name)) {
      assert.match(source, /ElMessageBox\.confirm\(record\.message/)
      assert.match(source, /confirmUnusedIssuance/)
      assert.match(source, /取消，不换钥/)
      assert.match(source, /keygenPolicy\?\.enabled === false/)
    }
    if (name.startsWith('generateHistory') || name.startsWith('keyVersionHistory')) assert.match(source, /row\.generation|\(row\.server \|\| row\.local\)\?\.generation/)
    if (name === 'generate/create' || name === 'keyupdate/index') {
      assert.match(source, /generateAndRegisterNodeKey/)
      assert.doesNotMatch(source, /await cryptoProvider\.generate\(/)
      assert.match(source, /KEYGEN_POLICY_DISABLED/)
      assert.match(source, /不会降级为普通生成/)
    }
  })
}
