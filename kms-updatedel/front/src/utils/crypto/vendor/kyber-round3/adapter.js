// Entropy adapter only: the pinned vendored round-3 cores preserve upstream polynomial math/encoding.
import { keygen as keygen512 } from './keygen512.js'
import { keygen as keygen768 } from './keygen768.js'
import { keygen as keygen1024 } from './keygen1024.js'

const CORES = { 512: keygen512, 768: keygen768, 1024: keygen1024 }

/** Consumes and best-effort wipes the caller's seed64 = d32 || z32, including on failure. */
export function keygenRound3FromSeed(seed, variant) {
  let privateArray
  try {
    if (!(seed instanceof Uint8Array) || seed.length !== 64) throw new Error('round-3 KeyGen 需要完整的 64 字节 d || z')
    if (typeof variant !== 'number' || ![512, 768, 1024].includes(variant)) throw new Error('round-3 KeyGen 只支持数值参数 512 / 768 / 1024')
    const core = CORES[variant]
    const [publicArray, secretArray] = core(seed.subarray(0, 32), seed.subarray(32, 64))
    privateArray = secretArray
    return { publicKey: Uint8Array.from(publicArray), secretKey: Uint8Array.from(secretArray) }
  } finally {
    try {
      if (Array.isArray(privateArray)) Array.prototype.fill.call(privateArray, 0)
    } finally {
      // Caller cleanup must survive output cleanup failure and overridden .fill methods.
      if (seed instanceof Uint8Array) Uint8Array.prototype.fill.call(seed, 0)
    }
  }
}
