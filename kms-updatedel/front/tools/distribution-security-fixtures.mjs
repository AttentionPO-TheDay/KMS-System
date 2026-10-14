// TEST ONLY: in-memory keys, no enrollment, issuance, HTTP or production key store.
// Real deployed crypto routines are used; this is not generation provenance evidence.
import { KeyGen768 } from 'crystals-kyber'
import { SM2 } from 'gm-crypto'
import { falcon512 } from '@noble/post-quantum/falcon.js'
import { BrowserCryptoProvider } from '../src/utils/crypto/browser-provider.js'

export class MemoryProbeProvider extends BrowserCryptoProvider {
  constructor() { super(); this.secrets = new Map(); this.readBuffers = [] }
  async _secretBytes(ref) {
    if (!this.secrets.has(ref)) throw new Error('TEST_ONLY secret missing')
    const copy = Uint8Array.from(this.secrets.get(ref))
    this.readBuffers.push(copy)
    return copy
  }
  dispose() {
    for (const value of this.secrets.values()) value.fill(0)
    for (const value of this.readBuffers) value.fill(0)
    this.secrets.clear(); this.readBuffers.length = 0
  }
}

export async function createDistributionFixtures({ includeFalcon = false } = {}) {
  const provider = new MemoryProbeProvider()
  const payloadKey = crypto.getRandomValues(new Uint8Array(16))
  const [pk, sk] = KeyGen768()
  provider.secrets.set('TEST_ONLY_KYBER', Uint8Array.from(sk))
  sk.fill(0)
  const kyber = await provider.wrapForPeer('KYBER', Uint8Array.from(pk).reduce((s, b) => s + b.toString(16).padStart(2, '0'), ''), payloadKey)
  const sm2Pair = SM2.generateKeyPair()
  provider.secrets.set('TEST_ONLY_SM2', Uint8Array.from(Buffer.from(sm2Pair.privateKey, 'hex')))
  const sm2 = await provider.wrapForPeer('SM2', sm2Pair.publicKey, payloadKey)
  const sscl = await provider.wrapForPeer('SSCL', sm2Pair.publicKey, payloadKey)
  if (includeFalcon) {
    const pair = falcon512.keygen()
    provider.secrets.set('TEST_ONLY_FALCON', pair.secretKey)
  }
  return { provider, payloadKey, kyber: kyber.envelope, sm2: sm2.envelope, sscl: sscl.envelope,
    dispose() { provider.dispose(); payloadKey.fill(0) } }
}

export function mutateBase64(value, index = 0) {
  const bytes = Buffer.from(value, 'base64')
  bytes[index < 0 ? bytes.length + index : index] ^= 1
  return bytes.toString('base64')
}
