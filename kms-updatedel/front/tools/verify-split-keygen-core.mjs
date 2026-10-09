// Safe oracle verification: fixed PUBLIC test seeds, in-memory ctypes only, no Django/DB/container writes.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import kyber from 'crystals-kyber'
import { falcon512 } from '@noble/post-quantum/falcon.js'
import { keygenRound3FromSeed } from '../src/utils/crypto/vendor/kyber-round3/adapter.js'

const hex = bytes => Buffer.from(bytes).toString('hex')
const hash = bytes => createHash('sha256').update(Uint8Array.from(bytes)).digest('hex')
const results = []
const fixtures = []
for (const variant of [512, 768, 1024]) {
  for (const sample of ['incrementing', 'zero', 'changed-d', 'changed-z']) {
    const seed = sample === 'zero' ? new Uint8Array(64) : Uint8Array.from({ length: 64 }, (_, i) => i)
    if (sample === 'changed-d') seed[0] ^= 1
    if (sample === 'changed-z') seed[32] ^= 1
    const seedHex = hex(seed)
    const pair = keygenRound3FromSeed(seed, variant)
    assert.ok(seed.every(byte => byte === 0), 'caller seed wiped')
    assert.equal(pair.publicKey.length, { 512: 800, 768: 1184, 1024: 1568 }[variant])
    assert.equal(pair.secretKey.length, { 512: 1632, 768: 2400, 1024: 3168 }[variant])
    assert.equal(hex(pair.secretKey.slice(-32)), seedHex.slice(64), 'z initialized at the exact FO offset')
    const [ct, ss] = kyber[`Encrypt${variant}`](pair.publicKey)
    assert.equal(hex(kyber[`Decrypt${variant}`](ct, pair.secretKey)), hex(ss), 'unchanged random encapsulation round-trip')
    const damaged = Uint8Array.from(ct); damaged[0] ^= 1
    const rejected = kyber[`Decrypt${variant}`](damaged, pair.secretKey)
    assert.notEqual(hex(rejected), hex(ss), 'damaged ciphertext rejected')
    fixtures.push({ variant, sample, seed: seedHex, pk: hex(pair.publicKey), sk: hex(pair.secretKey), ct: hex(ct), ss: hex(ss), damaged: hex(damaged), rejected: hex(rejected) })
    results.push({ variant, sample, pkSha256: hash(pair.publicKey), skSha256: hash(pair.secretKey) })
    pair.secretKey.fill(0)
  }
}
const frozen = JSON.parse(readFileSync(new URL('./fixtures/kyber-round3-oracle-v1.json', import.meta.url), 'utf8'))
for (const variant of [512, 768, 1024]) {
  const expected = frozen.vectors.find(value => value.variant === variant)
  const base = results.find(row => row.variant === variant && row.sample === 'incrementing')
  assert.equal(base.pkSha256, expected.pkSha256, 'frozen native public KAT')
  assert.equal(base.skSha256, expected.skSha256, 'frozen native private KAT')
  const d = results.find(row => row.variant === variant && row.sample === 'changed-d')
  const z = results.find(row => row.variant === variant && row.sample === 'changed-z')
  assert.notEqual(base.pkSha256, d.pkSha256)
  assert.notEqual(base.skSha256, d.skSha256)
  assert.equal(base.pkSha256, z.pkSha256)
  assert.notEqual(base.skSha256, z.skSha256)
}
assert.throws(() => keygenRound3FromSeed(new Uint8Array(63), 768), /64/)
const invalidSeed = new Uint8Array(64).fill(1)
assert.throws(() => keygenRound3FromSeed(invalidSeed, 999), /512/)
assert.ok(invalidSeed.every(value => value === 0))
for (const variant of ['toString', '__proto__', 'constructor', '768', null, undefined, {}, NaN, Infinity]) {
  const callerSeed = new Uint8Array(64).fill(7)
  assert.throws(() => keygenRound3FromSeed(callerSeed, variant), /512/)
  assert.ok(callerSeed.every(value => value === 0), 'adversarial variant failure wipes caller entropy')
}
for (const badSeed of [new Uint8Array(63).fill(7), new Uint8Array(65).fill(7)]) {
  assert.throws(() => keygenRound3FromSeed(badSeed, 768), /64/)
  assert.ok(badSeed.every(value => value === 0), 'wrong size entropy wiped')
}
for (const badType of [null, undefined, [], 'secret', new ArrayBuffer(64), new Int32Array(16)]) {
  assert.throws(() => keygenRound3FromSeed(badType, 768), /64/)
}
const overriddenFillSeed = new Uint8Array(64).fill(7)
overriddenFillSeed.fill = () => { throw new Error('caller override must not suppress wipe') }
assert.throws(() => keygenRound3FromSeed(overriddenFillSeed, 'toString'), /512/)
assert.ok(overriddenFillSeed.every(value => value === 0))

const falconSeed = Uint8Array.from({ length: 48 }, (_, i) => i)
let falconA, falconB
try {
  falconA = falcon512.keygen(falconSeed)
  falconB = falcon512.keygen(falconSeed)
  assert.equal(hex(falconA.publicKey), hex(falconB.publicKey))
  assert.equal(hex(falconA.secretKey), hex(falconB.secretKey))
} finally { falconSeed.fill(0) }
assert.equal(falconA.publicKey.length, 897)
assert.equal(falconA.secretKey.length, 1281)
const message = new TextEncoder().encode('KMS-SPLIT-KEYGEN-V1 public native compatibility probe')
const signature = falcon512.attached.seal(message, falconA.secretKey)
assert.equal(hex(falcon512.attached.open(signature, falconA.publicKey)), hex(message))
const damagedSignature = signature.slice(); damagedSignature[damagedSignature.length - 1] ^= 1
assert.throws(() => falcon512.attached.open(damagedSignature, falconA.publicKey))

if (process.argv.includes('--oracle')) {
  const script = String.raw`
import ctypes, hashlib, json, sys
if not __debug__:
    raise RuntimeError('Native crypto verification refuses optimized Python: assertions must execute')
payload = json.load(sys.stdin)
u8 = ctypes.c_ubyte
ptr = ctypes.POINTER(u8)
def buf(value):
    b = bytes.fromhex(value)
    return (u8 * len(b)).from_buffer_copy(b)
outputs = []
for f in payload['kyber']:
    v = f['variant']; lib = ctypes.CDLL('/backend/kyber/ref/lib/libpqcrystals_kyber%d_ref.so' % v)
    prefix = 'pqcrystals_kyber%d_ref_' % v
    keygen = getattr(lib, prefix + 'keypair_derand'); keygen.argtypes = [ptr, ptr, ptr]; keygen.restype = ctypes.c_int
    enc = getattr(lib, prefix + 'enc'); enc.argtypes = [ptr, ptr, ptr]; enc.restype = ctypes.c_int
    dec = getattr(lib, prefix + 'dec'); dec.argtypes = [ptr, ptr, ptr]; dec.restype = ctypes.c_int
    pk = (u8 * len(bytes.fromhex(f['pk'])))(); sk = (u8 * len(bytes.fromhex(f['sk'])))()
    assert keygen(pk, sk, buf(f['seed'])) == 0
    assert bytes(pk) == bytes.fromhex(f['pk']), 'native public bytes mismatch'
    assert bytes(sk) == bytes.fromhex(f['sk']), 'native private bytes mismatch'
    shared = (u8 * 32)()
    assert dec(shared, buf(f['ct']), sk) == 0 and bytes(shared) == bytes.fromhex(f['ss'])
    assert dec(shared, buf(f['damaged']), sk) == 0 and bytes(shared) == bytes.fromhex(f['rejected'])
    ct = (u8 * len(bytes.fromhex(f['ct'])))(); ss = (u8 * 32)()
    assert enc(ct, ss, pk) == 0
    outputs.append({'variant': v, 'sample': f['sample'], 'ct': bytes(ct).hex(), 'ss': bytes(ss).hex(), 'pkSha256': hashlib.sha256(bytes(pk)).hexdigest(), 'skSha256': hashlib.sha256(bytes(sk)).hexdigest()})
f = payload['falcon']; lib = ctypes.CDLL('/backend/falcon/falcon512/falcon512.dll')
open_fn = lib.crypto_sign_open; open_fn.argtypes = [ptr, ctypes.POINTER(ctypes.c_ulonglong), ptr, ctypes.c_ulonglong, ptr]; open_fn.restype = ctypes.c_int
sign_fn = lib.crypto_sign; sign_fn.argtypes = [ptr, ctypes.POINTER(ctypes.c_ulonglong), ptr, ctypes.c_ulonglong, ptr]; sign_fn.restype = ctypes.c_int
msg = (u8 * len(bytes.fromhex(f['sig'])))(); size = ctypes.c_ulonglong()
assert open_fn(msg, ctypes.byref(size), buf(f['sig']), len(bytes.fromhex(f['sig'])), buf(f['pk'])) == 0
assert bytes(msg[:size.value]) == bytes.fromhex(f['msg'])
assert open_fn(msg, ctypes.byref(size), buf(f['damaged']), len(bytes.fromhex(f['damaged'])), buf(f['pk'])) != 0
signed = (u8 * (len(bytes.fromhex(f['msg'])) + 2048))(); slen = ctypes.c_ulonglong()
assert sign_fn(signed, ctypes.byref(slen), buf(f['msg']), len(bytes.fromhex(f['msg'])), buf(f['sk'])) == 0
json.dump({'kyber': outputs, 'falconSigned': bytes(signed[:slen.value]).hex()}, sys.stdout)
`
  const input = { kyber: fixtures, falcon: { pk: hex(falconA.publicKey), sk: hex(falconA.secretKey), msg: hex(message), sig: hex(signature), damaged: hex(damagedSignature) } }
  const oracle = spawnSync('docker', ['exec', '-i', process.env.KMS_CRYPTO_ORACLE_CONTAINER || 'dvadmin3-django', 'python', '-c', script], { input: JSON.stringify(input), encoding: 'utf8', maxBuffer: 2 * 1024 * 1024 })
  if (oracle.status !== 0) throw new Error(`Native oracle FAILED (not skipped): ${oracle.stderr || oracle.error || oracle.status}`)
  const optimized = spawnSync('docker', ['exec', '-i', '-e', 'PYTHONOPTIMIZE=1', process.env.KMS_CRYPTO_ORACLE_CONTAINER || 'dvadmin3-django', 'python', '-c', script], { input: JSON.stringify(input), encoding: 'utf8', maxBuffer: 2 * 1024 * 1024 })
  assert.notEqual(optimized.status, 0, 'optimized Python must not falsely pass the native crypto gate')
  assert.match(optimized.stderr, /refuses optimized Python/)
  const native = JSON.parse(oracle.stdout)
  assert.equal(native.kyber.length, 12)
  for (const output of native.kyber) {
    const fixture = fixtures.find(value => value.variant === output.variant && value.sample === output.sample)
    assert.equal(hex(kyber[`Decrypt${output.variant}`](Buffer.from(output.ct, 'hex'), Buffer.from(fixture.sk, 'hex'))), output.ss, 'native encapsulation -> JS decapsulation')
  }
  assert.equal(hex(falcon512.attached.open(Buffer.from(native.falconSigned, 'hex'), falconA.publicKey)), hex(message), 'native Falcon signature -> noble round-3 open')
  console.info('Native oracle PASS: all 12 public AND private byte comparisons; d/z sensitivity; bidirectional random KEM; damaged-ciphertext rejection; seeded Falcon native bidirectional signatures/tamper rejection')
  console.info(JSON.stringify(results.filter(value => value.sample === 'incrementing'), null, 2))
} else console.info('Local seeded core PASS: 12 KEM fixtures, all variants, d/z sensitivity, caller wipe, random KEM round-trips/damage, Falcon seed48 deterministic/round-trip. Native gate NOT run; use --oracle.')
falconA.secretKey.fill(0); falconB.secretKey.fill(0)
