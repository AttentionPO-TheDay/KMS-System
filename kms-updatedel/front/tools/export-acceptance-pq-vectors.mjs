// Public, isolated interoperability vectors. Never uses browser storage or business keys.
import { readFileSync, writeFileSync } from 'node:fs'
import kyber from 'crystals-kyber'
import { falcon512 } from '@noble/post-quantum/falcon.js'
import { keygenRound3FromSeed } from '../src/utils/crypto/vendor/kyber-round3/adapter.js'

const hex = value => Buffer.from(value).toString('hex')
const source = JSON.parse(readFileSync(new URL('./fixtures/kyber-round3-oracle-v1.json', import.meta.url)))
const vectors = source.vectors.map(vector => {
  const pair = keygenRound3FromSeed(Uint8Array.from({ length: 64 }, (_, i) => i), vector.variant)
  try {
    const [ct, ss] = kyber[`Encrypt${vector.variant}`](pair.publicKey)
    return { ...vector, ciphertextHex: hex(ct), sharedSecretHex: hex(ss) }
  } finally { pair.secretKey.fill(0) }
})
const pair = falcon512.keygen(Uint8Array.from({ length: 48 }, (_, i) => i))
const message = new TextEncoder().encode('KMS acceptance PUBLIC interoperability vector v1')
try {
  const signed = falcon512.attached.seal(message, pair.secretKey)
  const result = {
    version: 1,
    source: 'KYBER round-3: production JS adapter + crystals-kyber; FALCON-512: @noble/post-quantum',
    scope: 'Public test entropy and test shared secrets only. Not FIPS 203 ML-KEM vectors.',
    seedHex: source.seedHex,
    kyber: vectors,
    falcon: { publicKeyHex: hex(pair.publicKey), messageHex: hex(message), signedMessageHex: hex(signed) }
  }
  writeFileSync(new URL('../../../kms-distribute/dvadmin/backend/pqkds/acceptance_pq_vectors.json', import.meta.url), JSON.stringify(result, null, 2) + '\n')
  console.log('Exported public KYBER 512/768/1024 and FALCON-512 interoperability vectors; no private keys exported.')
} finally { pair.secretKey.fill(0) }
