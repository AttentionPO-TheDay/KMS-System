// Reproduce the minimal deterministic KeyGen vendor from installed crystals-kyber@5.1.0.
// This never edits node_modules. Kept as an audit/reproducibility tool, not a build step.
import fs from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { parse } from '@babel/parser'

const front = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const upstream = path.join(front, 'node_modules/crystals-kyber')
const target = path.join(front, 'src/utils/crypto/vendor/kyber-round3')
const pkg = JSON.parse(fs.readFileSync(path.join(upstream, 'package.json'), 'utf8'))
if (pkg.version !== '5.1.0') throw new Error('Vendor source must be crystals-kyber@5.1.0')
fs.mkdirSync(target, { recursive: true })
fs.copyFileSync(path.join(upstream, 'LICENSE'), path.join(target, 'LICENSE'))
const pinnedHashes = { 512: 'a3a8a4bcb307d73e9f9ebeeb1c06aa38077ddddb342a8af17d48cbb951ba7312', 768: '9c40a561522406d053c19aedd6ae39b2c322ca16cf5112e095b2542b91dfcf8c', 1024: '52dcdd5d8f0869f97b111a51491a37c2f3984d1069371c9a3b41fa542332ec27' }
const manifest = { package: 'crystals-kyber', version: '5.1.0', repository: 'https://github.com/antontutoveanu/crystals-kyber-javascript', license: 'MIT', files: {} }
for (const variant of [512, 768, 1024]) {
  const source = fs.readFileSync(path.join(upstream, `kyber${variant}.js`), 'utf8')
  manifest.files[`kyber${variant}.js`] = createHash('sha256').update(source).digest('hex')
  if (manifest.files[`kyber${variant}.js`] !== pinnedHashes[variant]) throw new Error(`Pinned upstream source hash mismatch: ${variant}`)
  const ast = parse(source, { sourceType: 'script' })
  const functions = new Map(ast.program.body.filter(n => n.type === 'FunctionDeclaration').map(n => [n.id.name, n]))
  const keygen = ast.program.body.find(n => n.type === 'ExpressionStatement' && n.expression.left?.name === `KeyGen${variant}`)
  const selected = new Set()
  function visit(node) {
    if (!node || typeof node !== 'object') return
    if (node.type === 'Identifier' && functions.has(node.name) && !selected.has(node.name)) {
      selected.add(node.name)
      visit(functions.get(node.name).body)
    }
    for (const [key, value] of Object.entries(node)) {
      if (['loc', 'start', 'end', 'comments'].includes(key)) continue
      if (Array.isArray(value)) value.forEach(visit)
      else if (value && typeof value === 'object') visit(value)
    }
  }
  visit(keygen)
  let keygenText = source.slice(keygen.start, keygen.end)
    .replace(`KeyGen${variant} = function()`, 'export function keygen(d, z)')
    .replace('indcpaKeyGen()', 'indcpaKeyGen(d)')
    .replace(/let rnd = new Uint8Array\(32\);\s*webcrypto.getRandomValues\(rnd\);[^\n]*/, 'let rnd = z; // Explicit 32-byte FO rejection entropy; no RNG hook.')
  let declarations = ast.program.body.filter(n => n.type === 'VariableDeclaration' && !source.slice(n.start, n.end).includes('require('))
    .filter(n => n.declarations.some(d => d.id.name !== 'nttZetasInv'))
    .map(n => source.slice(n.start, n.end)).join('\n\n')
  const functionText = [...functions].filter(([name]) => selected.has(name)).map(([name, node]) => {
    let text = source.slice(node.start, node.end)
    if (name === 'indcpaKeyGen') text = text.replace('indcpaKeyGen()', 'indcpaKeyGen(d)')
      .replace(/let rnd = new Uint8Array\(32\);\s*webcrypto.getRandomValues\(rnd\);[^\n]*/, 'let rnd = d; // Explicit 32-byte CPA entropy, hashed exactly as round-3.')
    return text
  }).join('\n\n')
  const header = `/**\n * Minimal KeyGen dependency closure from crystals-kyber@5.1.0 kyber${variant}.js.\n * Copyright (c) 2020 Anton Tutoveanu; MIT license in ./LICENSE.\n * Upstream SHA-256: ${manifest.files[`kyber${variant}.js`]}\n * Changes: ESM/local Buffer imports; explicit d32/z32 instead of RNG calls;\n * unused encapsulation/decapsulation/test functions removed. Core math/encoding retained.\n * Input validation and temporary-buffer cleanup belong to ./adapter.js.\n */\nimport sha3 from 'sha3'\nimport { Buffer } from 'buffer'\nconst { SHA3, SHAKE } = sha3\n\n`
  fs.writeFileSync(path.join(target, `keygen${variant}.js`), header + declarations + '\n\n' + keygenText + '\n\n' + functionText + '\n')
}
fs.writeFileSync(path.join(target, 'SOURCE.json'), JSON.stringify(manifest, null, 2) + '\n')
console.info('Vendored pinned deterministic round-3 KeyGen dependency closures for 512/768/1024')
