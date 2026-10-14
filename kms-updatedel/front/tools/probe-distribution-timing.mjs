#!/usr/bin/env node
// Diagnostic only: randomized, equal-size two-class timing samples and Welch t.
// Node/V8 results do not certify browser constant time or physical side channels.
import { randomInt } from 'node:crypto'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import os from 'node:os'
import { sm4GcmEncrypt, sm4GcmDecrypt } from '../src/utils/sm4.js'
import { createDistributionFixtures, mutateBase64 } from './distribution-security-fixtures.mjs'

const args = process.argv.slice(2)
const options = { profile: 'sm4-tag', samples: 10000, rounds: 3, output: null }
for (let i = 0; i < args.length; i += 2) {
  const name = args[i]?.replace(/^--/, '')
  if (!Object.hasOwn(options, name) || args[i + 1] === undefined) throw new Error('Use --profile sm4-tag|sm4-key|kyber-envelope|all --samples N --rounds N --output FILE')
  options[name] = name === 'samples' || name === 'rounds' ? Number(args[i + 1]) : args[i + 1]
}
if (!Number.isInteger(options.samples) || options.samples < 20 || options.samples > 1000000 || !Number.isInteger(options.rounds) || options.rounds < 1 || options.rounds > 20) throw new Error('samples must be 20..1000000 per class per round; rounds must be 1..20')
const profiles = options.profile === 'all' ? ['sm4-tag', 'sm4-key', 'kyber-envelope'] : [options.profile]
if (profiles.some(p => !['sm4-tag', 'sm4-key', 'kyber-envelope'].includes(p))) throw new Error('Unknown timing profile')

function accumulator() {
  let n = 0; let mean = 0; let m2 = 0
  return {
    push(value) { n++; const delta = value - mean; mean += delta / n; m2 += delta * (value - mean) },
    result() { return { n, meanNs: mean, varianceNs: n > 1 ? m2 / (n - 1) : 0 } }
  }
}
function shuffledLabels() {
  const labels = Array.from({ length: options.samples * 2 }, (_, i) => i % 2)
  for (let i = labels.length - 1; i > 0; i--) { const j = randomInt(i + 1); [labels[i], labels[j]] = [labels[j], labels[i]] }
  return labels
}
function compare(classes) {
  const [a, b] = classes.map(x => x.result())
  const denominator = Math.sqrt(a.varianceNs / a.n + b.varianceNs / b.n)
  const welchT = denominator ? (a.meanNs - b.meanNs) / denominator : null
  return { classes: [a, b], welchT,
    status: options.samples < 10000 ? 'exploratory_small_sample' : welchT === null ? 'inconclusive' : Math.abs(welchT) >= 4.5 ? 'timing_difference_detected' : 'no_difference_detected_in_this_run' }
}

async function runProfile(profile) {
  const fixedKey = crypto.getRandomValues(new Uint8Array(16))
  const plaintext = new Uint8Array(16)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const { ciphertext, tag } = sm4GcmEncrypt(fixedKey, plaintext, iv)
  const tags = [Uint8Array.from(tag), Uint8Array.from(tag)]; tags[0][0] ^= 1; tags[1][15] ^= 1
  const fixture = profile === 'kyber-envelope' ? await createDistributionFixtures() : null
  const envelopes = fixture ? [0, -1].map(index => ({ ...fixture.kyber, tag: mutateBase64(fixture.kyber.tag, index) })) : null
  const measure = async row => {
    let value; let failed = false; let code
    const start = process.hrtime.bigint()
    try {
      if (profile === 'sm4-key') value = sm4GcmEncrypt(row.key, plaintext, iv)
      else if (profile === 'sm4-tag') value = sm4GcmDecrypt(fixedKey, ciphertext, iv, tags[row.label])
      else value = await fixture.provider.unwrapEnvelope('KYBER', 'TEST_ONLY_KYBER', envelopes[row.label])
    } catch (error) { failed = true; code = error?.code }
    const elapsed = Number(process.hrtime.bigint() - start)
    // Functional checks/cleanup stay outside the measured interval.
    if (profile === 'sm4-key') {
      if (failed || value?.ciphertext?.length !== 16) throw new Error('Unexpected encryption failure')
      value.tag.fill(0)
    } else if (!failed || (profile === 'kyber-envelope' && code !== 'NODE_ENVELOPE_UNWRAP_FAILED')) throw new Error('Expected uniform authentication failure')
    if (fixture) fixture.provider.readBuffers.length = 0
    return elapsed
  }
  const rounds = []
  try {
    const warmRows = [{ label: 0, key: fixedKey }, { label: 1, key: fixedKey }]
    for (let i = 0; i < 512; i++) await measure(warmRows[i % 2])
    for (let round = 0; round < options.rounds; round++) {
      // All labels and random keys prepared before timing; classes are interleaved.
      const rows = shuffledLabels().map(label => ({ label, key: profile === 'sm4-key' ? (label ? crypto.getRandomValues(new Uint8Array(16)) : Uint8Array.from(fixedKey)) : null }))
      const classes = [accumulator(), accumulator()]
      try {
        for (const row of rows) classes[row.label].push(await measure(row))
      } finally { for (const row of rows) row.key?.fill(0) }
      rounds.push({ round: round + 1, ...compare(classes) })
    }
    return { profile, classMeaning: profile === 'sm4-key' ? ['fixed key', 'random key; same payload size'] : ['invalid tag at first byte', 'invalid tag at last byte; same ciphertext'], rounds }
  } finally {
    fixture?.dispose(); fixedKey.fill(0); plaintext.fill(0); tag.fill(0); tags.forEach(t => t.fill(0))
  }
}
const lock = JSON.parse(await readFile(new URL('../package-lock.json', import.meta.url), 'utf8'))
const report = { recordedAt: new Date().toISOString(), environment: { node: process.version, v8: process.versions.v8, platform: process.platform, arch: process.arch, cpu: os.cpus()[0]?.model,
  cryptoLibraries: Object.fromEntries(['crystals-kyber', '@noble/post-quantum', 'gm-crypto'].map(name => [name, lock.packages[`node_modules/${name}`]?.version])) },
  parameters: options, profiles: [], limitation: 'Diagnostic only. Equal-sized invalid tags avoid comparing successful decryption with early rejection. No certificate of constant time, cache/power/EM resistance or target-browser behavior. Repeat on an isolated target CPU; do not discard adverse runs.' }
for (const profile of profiles) report.profiles.push(await runProfile(profile))
const json = JSON.stringify(report, null, 2) + '\n'
if (options.output) { const target = resolve(options.output); await mkdir(dirname(target), { recursive: true }); await writeFile(target, json) }
console.log(json)
if (report.profiles.some(p => p.rounds.some(r => r.status === 'timing_difference_detected'))) process.exitCode = 2
