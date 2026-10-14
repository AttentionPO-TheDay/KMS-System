import assert from 'node:assert/strict'
import { inspectFalconEncryption } from '../src/utils/falcon-encryption-state.js'
import { encodeMaterial } from '../src/utils/crypto/falcon-cl-v1.js'

const node = { nodeId: 'isolated-falcon', status: 'ACTIVE', falconClCapability: { enabled: true } }
const inspect = (keys, locals = [], extra = {}) => inspectFalconEncryption({ node, keys, locals, hasKey: async () => true, ...extra })
const signing = { algorithm: 'FALCON', purpose: 'SIGN', allowsNewWork: true,
  generation: { schemeId: 'KMS_SPLIT_SIGN_V1', schemeVersion: 1 } }
assert((await inspect([signing])).canAdd, 'split signing does not establish encryption capability')
assert(!(await inspect([signing], [], { node: { ...node, status: 'PENDING_INIT' } })).canAdd)
assert(!(await inspect([], [], { node: { ...node, falconClCapability: { enabled: false } } })).canAdd)
// Nonzero matrices test material identification, not cryptographic security.
const matrix = new Int32Array(512 * 1024).fill(2)
const publicKey = encodeMaterial({ A: matrix, B: matrix, H_id: matrix, U_id: matrix }, 'PUBLIC', node.nodeId)
const encryption = { algorithm: 'FALCON_CL_V1', purpose: 'ENCRYPT', materialVersion: 1,
  keyId: 'enc-1', keyVersion: 1, publicKey, allowsNewWork: true,
  generation: { schemeId: 'KMS_SPLIT_FALCON_CL_V1', schemeVersion: 1 } }
const local = { algorithm: 'FALCON_CL_V1', keyId: 'enc-1', version: 1, publicKey, keyRef: 'isolated' }
const ready = await inspect([signing, encryption], [local])
assert(ready.ready)
assert(!ready.canAdd)
assert(!(await inspect([encryption])).ready, 'registry-only is not locally usable')
assert(!(await inspect([{ ...encryption, publicKey: 'invalid' }], [local])).ready)
assert(!(await inspect([{ ...encryption, purpose: 'SIGN' }], [local])).ready)
assert(!(await inspect([{ ...encryption, generation: signing.generation }], [local])).ready)
assert(!(await inspect([{ ...encryption, allowsNewWork: false }], [local])).canAdd, 'history is not permission to reset')
assert(!(await inspect([encryption], [local], { hasKey: async () => false })).ready)
assert((await inspect([], [local])).pending)
console.log('PASS: 已激活节点补充入口、签名/加密识别、真实材料契约、已有登记防重复、本机缺失和失败恢复状态')
