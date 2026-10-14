// Experimental custom matrix encryption. Not Falcon signatures, FN-DSA or a proven KEM.
export const FALCON_CL_ALGORITHM = 'FALCON_CL_V1'
export const FALCON_CL_PARAMS = Object.freeze({ n: 512, m: 1024, q: 12289 })
const { n: N, m: M, q: Q } = FALCON_CL_PARAMS
const MAX_MATERIAL = 8000000
const CT_BYTES = 21 + 3 * M * 8
const encoder = new TextEncoder()
const decoder = new TextDecoder('utf-8', { fatal: true })
const layouts = { PUBLIC: ['A', 'B', 'H_id', 'U_id'], PARTIAL: ['A', 'B', 'H_id', 'D_id'], PRIVATE: ['D_id', 'S_id'] }

export function encodeB64(bytes) {
  let text = ''
  for (let i = 0; i < bytes.length; i += 4096) text += String.fromCharCode(...bytes.subarray(i, i + 4096))
  return btoa(text)
}
function decodeB64(value, limit) {
  if (typeof value !== 'string' || value.length > Math.ceil(limit / 3) * 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw new Error('Falcon CL encoding/size invalid')
  const bytes = Uint8Array.from(atob(value), c => c.charCodeAt(0))
  if (bytes.length > limit || encodeB64(bytes) !== value) throw new Error('Falcon CL encoding noncanonical')
  return bytes
}
function secretField(field) { return field === 'D_id' || field === 'S_id' }
export function parseMaterial(value, kind, nodeId = null) {
  if (typeof value !== 'string' || value.length > MAX_MATERIAL || !layouts[kind]) throw new Error('Falcon CL material size/kind invalid')
  const text = decoder.decode(decodeB64(value, MAX_MATERIAL))
  const data = JSON.parse(text)
  // Also rejects duplicate JSON fields, alternative escaping and noncanonical numbers.
  if (text !== JSON.stringify(data)) throw new Error('Falcon CL noncanonical JSON')
  const fields = layouts[kind]
  const allowed = ['algorithm', 'purpose', 'version', 'parameters', 'nodeId', 'kind', ...fields]
  if (!data || Object.keys(data).length !== allowed.length || Object.keys(data).some(k => !allowed.includes(k)) || data.algorithm !== FALCON_CL_ALGORITHM || data.purpose !== 'ENCRYPT' || data.version !== 1 || JSON.stringify(data.parameters) !== JSON.stringify(FALCON_CL_PARAMS) || data.kind !== kind || typeof data.nodeId !== 'string' || !data.nodeId || (nodeId !== null && data.nodeId !== nodeId)) throw new Error('Falcon CL material contract invalid')
  const out = { nodeId: data.nodeId }
  for (const field of fields) {
    const secret = secretField(field)
    const count = (secret ? M : N) * M
    const bytes = decodeB64(data[field], count * (secret ? 1 : 2))
    if (bytes.length !== count * (secret ? 1 : 2)) throw new Error('Falcon CL matrix shape invalid')
    const view = new DataView(bytes.buffer)
    const values = new Int32Array(count)
    for (let i = 0; i < count; i++) {
      const v = secret ? view.getInt8(i) : view.getUint16(i * 2, true)
      if (secret ? Math.abs(v) > 8 : v >= Q) throw new Error('Falcon CL matrix range invalid')
      values[i] = v
    }
    out[field] = values
  }
  return out
}
export function encodeMaterial(matrices, kind, nodeId) {
  const data = { algorithm: FALCON_CL_ALGORITHM, purpose: 'ENCRYPT', version: 1, parameters: FALCON_CL_PARAMS, nodeId, kind }
  for (const field of layouts[kind]) {
    const secret = secretField(field)
    const source = matrices[field]
    const bytes = new Uint8Array(source.length * (secret ? 1 : 2))
    const view = new DataView(bytes.buffer)
    for (let i = 0; i < source.length; i++) {
      if (secret) view.setInt8(i, source[i])
      else view.setUint16(i * 2, source[i], true)
    }
    data[field] = encodeB64(bytes)
  }
  return encodeB64(encoder.encode(JSON.stringify(data)))
}
const mod = value => ((value % Q) + Q) % Q
// Number integer products remain exact: maximum sum < 512*12288^2 < 2^53.
function transposeVector(matrix, vector, rows) {
  const out = new Float64Array(M)
  for (let row = 0; row < rows; row++) {
    const scale = vector[row]
    if (scale === 0) continue
    const offset = row * M
    for (let col = 0; col < M; col++) out[col] += matrix[offset + col] * scale
  }
  return out
}
function multiply(a, s) {
  const out = new Int32Array(N * M)
  for (let row = 0; row < N; row++) {
    const sums = new Float64Array(M)
    for (let k = 0; k < M; k++) {
      const scale = a[row * M + k]
      const offset = k * M
      for (let col = 0; col < M; col++) sums[col] += scale * s[offset + col]
    }
    for (let col = 0; col < M; col++) out[row * M + col] = mod(sums[col])
  }
  return out
}
function randomWords(count) {
  const words = new Uint32Array(count)
  for (let i = 0; i < count; i += 16384) crypto.getRandomValues(words.subarray(i, Math.min(count, i + 16384)))
  return words
}
function uniform(count) {
  const out = new Int32Array(count)
  const limit = 4294967296 - (4294967296 % Q)
  let index = 0
  while (index < count) {
    for (const word of randomWords(count - index + 16)) {
      if (word < limit && index < count) out[index++] = word % Q
    }
  }
  return out
}
function roundEven(value) {
  const floor = Math.floor(value)
  const frac = value - floor
  return frac === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(value)
}
function short(count) {
  const out = new Int32Array(count)
  let index = 0
  while (index < count) {
    const words = randomWords((count - index) * 2)
    for (let i = 0; i < words.length && index < count; i += 2) {
      const u1 = (words[i] + 1) / 4294967297
      const u2 = (words[i + 1] + 1) / 4294967297
      const value = roundEven(Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * 1.17)
      if (Math.abs(value) <= 8) out[index++] = value
    }
  }
  return out
}
export function completePartial(partialKey, nodeId) {
  const partial = parseMaterial(partialKey, 'PARTIAL', nodeId)
  const s = short(M * M)
  try {
    const u = multiply(partial.B, s)
    // Build public and secret packages independently: never spread D_id into
    // the public package, even if its encoder layout changes later.
    const publicKey = encodeMaterial({ A: partial.A, B: partial.B, H_id: partial.H_id, U_id: u }, 'PUBLIC', nodeId)
    const privateKey = encodeMaterial({ D_id: partial.D_id, S_id: s }, 'PRIVATE', nodeId)
    return { publicKey, privateKey }
  } finally { s.fill(0); partial.D_id.fill(0) }
}
export function decodeCiphertext(value) {
  const bytes = decodeB64(value, CT_BYTES)
  if (bytes.length !== CT_BYTES || decoder.decode(bytes.subarray(0, 5)) !== 'FCTV2') throw new Error('Falcon CL ciphertext header/length invalid')
  const view = new DataView(bytes.buffer)
  if (view.getUint32(5, true) !== N || view.getUint32(9, true) !== M || view.getUint32(13, true) !== Q || view.getUint32(17, true) !== 16) throw new Error('Falcon CL ciphertext parameters invalid')
  const vectors = Array.from({ length: 3 }, () => new Int32Array(M))
  for (let i = 0; i < 3 * M; i++) {
    const value = view.getBigInt64(21 + i * 8, true)
    if (value < 0n || value >= BigInt(Q)) throw new Error('Falcon CL ciphertext range invalid')
    vectors[Math.floor(i / M)][i % M] = Number(value)
  }
  return vectors
}
export function encrypt(publicKey, payloadKey, recipientId = null) {
  if (!(payloadKey instanceof Uint8Array) || payloadKey.length !== 16) throw new Error('Falcon CL requires exactly 16 bytes')
  const pk = parseMaterial(publicKey, 'PUBLIC', recipientId)
  const r1 = uniform(N); const r2 = uniform(N)
  const a = transposeVector(pk.A, r1, N); const b = transposeVector(pk.B, r2, N)
  const h = transposeVector(pk.H_id, r1, N); const u = transposeVector(pk.U_id, r2, N)
  const e1 = short(M); const e2 = short(M); const e3 = short(M)
  const bytes = new Uint8Array(CT_BYTES)
  bytes.set(encoder.encode('FCTV2'))
  const view = new DataView(bytes.buffer)
  for (const [offset, value] of [[5, N], [9, M], [13, Q], [17, 16]]) view.setUint32(offset, value, true)
  for (let i = 0; i < M; i++) {
    const bit = i < 128 ? ((payloadKey[i >> 3] >> (7 - (i % 8))) & 1) : 0
    view.setBigInt64(21 + i * 8, BigInt(mod(a[i] + e1[i])), true)
    view.setBigInt64(21 + (M + i) * 8, BigInt(mod(b[i] + e2[i])), true)
    view.setBigInt64(21 + (2 * M + i) * 8, BigInt(mod(h[i] + u[i] + e3[i] + Math.floor(Q / 2) * bit)), true)
  }
  return encodeB64(bytes)
}
export function decrypt(privateKey, ciphertext, recipientId = null) {
  const sk = parseMaterial(privateKey, 'PRIVATE', recipientId)
  try {
    const [c1, c2, c3] = decodeCiphertext(ciphertext)
    const d = transposeVector(sk.D_id, c1, M); const s = transposeVector(sk.S_id, c2, M)
    const out = new Uint8Array(16)
    const half = Math.floor(Q / 2)
    for (let i = 0; i < 128; i++) {
      const value = mod(c3[i] - mod(d[i]) - mod(s[i]))
      const distHalf = Math.min(Math.abs(value - half), Math.abs(value - half + Q), Math.abs(value - half - Q))
      if (distHalf < Math.min(value, Q - value)) out[i >> 3] |= 1 << (7 - (i % 8))
    }
    return out
  } finally { sk.D_id.fill(0); sk.S_id.fill(0) }
}
export async function materialFingerprint(value, kind) {
  parseMaterial(value, kind)
  const bytes = encoder.encode(`${FALCON_CL_ALGORITHM}|ENCRYPT|1|512|1024|12289|${kind}|${value}`)
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
}
