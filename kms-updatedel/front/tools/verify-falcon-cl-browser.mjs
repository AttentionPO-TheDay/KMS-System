#!/usr/bin/env node
// Real browser ESM/Worker + native Python oracle. TEST_ONLY material stays in
// process memory/isolated browser profile; no server API or production DB used.
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)))
const backend = resolve(root, 'kms-distribute/dvadmin/backend').replaceAll('\\', '/')
const base = process.env.FALCON_BROWSER_BASE || 'http://127.0.0.1:5184'
const cdp = process.env.FALCON_CDP || 'http://127.0.0.1:9234'
const dockerArgs = ['run', '--rm', '-i', '--network', 'none', '--mount', `type=bind,source=${backend}/pqkds,target=/backend/pqkds,readonly`, '--mount', `type=bind,source=${backend}/tests,target=/backend/tests,readonly`, '--tmpfs', '/backend/logs', '--workdir', '/backend', '--entrypoint', 'python', 'kms-dvadmin3-django:local', '-B', '/backend/tests/falcon_cl_oracle.py']
function oracle(mode, input) {
  const result = spawnSync('docker', [...dockerArgs, mode, mode === 'create' ? '/dev/stdout' : '/dev/stdin'], { input: input || '', encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 180000 })
  if (result.status !== 0) throw new Error(`Native oracle failed: ${result.stderr?.slice(-3000)}`)
  if (result.stderr) console.log(result.stderr.trim())
  return mode === 'create' ? JSON.parse(result.stdout) : result.stdout.trim()
}
const fixture = oracle('create')
assert.equal(fixture.testOnly, true)
const target = await (await fetch(`${cdp}/json/new?${encodeURIComponent(base)}`, { method: 'PUT' })).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', ev => {
  const message = JSON.parse(ev.data)
  if (pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id); pending.delete(message.id)
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result)
  }
})
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }))
function send(method, params = {}) { return new Promise((resolve, reject) => { const requestId = ++id; pending.set(requestId, { resolve, reject }); ws.send(JSON.stringify({ id: requestId, method, params })) }) }
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
  return result.result.value
}
try {
  await send('Page.enable'); await send('Runtime.enable')
  await send('Page.navigate', { url: base })
  await evaluate('new Promise(resolve => document.readyState === "complete" ? resolve() : addEventListener("load", resolve, {once:true}))')
  await evaluate(`globalThis.__FALCON_TEST_ONLY = ${JSON.stringify(fixture)}; true`)
  const result = await evaluate(`(async () => {
    const f = globalThis.__FALCON_TEST_ONLY
    const matrix = await import('/src/utils/crypto/falcon-cl-v1.js')
    const { runFalconWorker } = await import('/src/utils/crypto/falcon-cl-browser.js')
    const { cryptoProvider: provider, toHex } = await import('/src/utils/crypto/browser-provider.js')
    const { buildKeyRef } = await import('/src/utils/crypto/key-ref.js')
    const { buildNodeEnvelope, signNodeEnvelope, keyHashOf } = await import('/src/utils/crypto/envelope-signing.js')
    const { verifyNodeEnvelope, checkRecoveredKeyHash, nodeProof } = await import('/src/utils/crypto/node-envelope.js')
    const checks = []
    const check = (name, ok) => { if (!ok) throw new Error(name); checks.push(name) }
    const rejected = (name, fn) => { let failed = false; try { fn() } catch { failed = true }; check(name, failed) }
    const nodeId = 'TEST_ONLY_FALCON_RECIPIENT'
    const key = Uint8Array.from({length:16}, (_,i) => i)
    check('Python -> browser exact 16 bytes', toHex(matrix.decrypt(f.privateKey, f.ciphertext, nodeId)) === f.keyHex)
    check('original reference FCTV2 -> browser exact 16 bytes', toHex(matrix.decrypt(f.privateKey, f.referenceCiphertext, nodeId)) === f.keyHex)
    const ref = buildKeyRef({nodeId, algorithm:'FALCON_CL_V1', keyId:'TEST_ONLY_FCL', version:1})
    await provider.importSecret(ref, {algorithm:'FALCON_CL_V1',secret:f.privateKey,publicKey:f.publicKey})
    const { envelope } = await provider.wrapForPeer('FALCON_CL_V1', f.publicKey, key)
    check('browser provider Worker wrap -> Worker unwrap exact bytes', toHex(await provider.unwrapEnvelope('FALCON_CL_V1', ref, envelope)) === f.keyHex)
    const complete = await runFalconWorker('completePartial', [f.partial, nodeId])
    const browserCt = await runFalconWorker('encrypt', [complete.publicKey, key, nodeId])
    check('browser-local CSPRNG S -> U -> encryption -> decrypt', toHex(await runFalconWorker('decrypt',[complete.privateKey,browserCt,nodeId])) === f.keyHex)
    const generationRef = buildKeyRef({nodeId,algorithm:'FALCON_CL_V1',keyId:'TEST_ONLY_GENERATED',version:1})
    const identity = {nodeId,userId:'102',bindingKind:'DEMO',deviceFingerprint:'',demoSessionId:'TEST_ONLY_SESSION_HASH',demoRevision:'1'}
    const generated = await provider.generate('FALCON_CL_V1', {nodeId,keyId:'TEST_ONLY_GENERATED',version:1,generationContext:identity, issueKeygen: async request => {
      const generationIssuanceId = crypto.randomUUID()
      return {generationScheme:'KMS_SPLIT_FALCON_CL_V1', generationIssuanceId, authorizationTicketId:crypto.randomUUID(),partialMaterial:f.partial,expiresAt:new Date(Date.now()+60000).toISOString(),context:{schemeId:'KMS_SPLIT_FALCON_CL_V1',schemeVersion:'1',coreFamily:'FALCON_CL_V1',variant:'512',...identity,keyId:request.keyId,keyVersion:'1',purpose:'ENCRYPT',generationIssuanceId}}
    }})
    check('provider generate seals independent full secret locally',generated.keyRef === generationRef && !Object.hasOwn(generated,'privateKey') && !Object.hasOwn(generated,'S_id'))
    check('local authenticated matrix material survives readback',(await provider.selfTest('FALCON_CL_V1',generationRef)).ok)
    const noble = await import('/node_modules/@noble/post-quantum/falcon.js')
    const signer = noble.falcon512.keygen()
    const signRef = buildKeyRef({nodeId:'TEST_ONLY_SENDER',algorithm:'FALCON',keyId:'TEST_ONLY_SIGN',version:1})
    await provider.importSecret(signRef,{algorithm:'FALCON',secret:toHex(signer.secretKey),publicKey:toHex(signer.publicKey)})
    signer.secretKey.fill(0)
    const built = await buildNodeEnvelope({provider,wrapping:'FALCON_CL_V1',recipientPublicKeyHex:f.publicKey,payloadKey:key,batchId:'dist-20261012000000-12345678',senderNodeId:'TEST_ONLY_SENDER',receiverNodeId:nodeId,recipientKeyId:'TEST_ONLY_FCL',recipientKeyVersion:1,expiresAt:new Date(Date.now()+60000).toISOString()})
    const signatureB64 = await signNodeEnvelope(provider,signRef,built.envelope)
    check('existing standard Falcon sign -> verify new encrypted envelope',(await verifyNodeEnvelope({provider,envelope:built.envelope,signatureB64,senderFalconPublicKeyHex:toHex(signer.publicKey)})).ok)
    check('signed-field tamper rejected before decrypt',!(await verifyNodeEnvelope({provider,envelope:{...built.envelope,key_hash:'0'.repeat(64)},signatureB64,senderFalconPublicKeyHex:toHex(signer.publicKey)})).ok)
    const recovered = await provider.unwrapEnvelope('FALCON_CL_V1',ref,built.envelope)
    check('recovered keyHash exact',(await checkRecoveredKeyHash(recovered,built.envelope)).ok)
    check('both existing HMAC confirmations equal',await nodeProof({payloadKey:key,sessionId:'TEST_ONLY_SESSION'}) === await nodeProof({payloadKey:recovered,sessionId:'TEST_ONLY_SESSION'}))
    check('wrong key HMAC confirmation cannot match',await nodeProof({payloadKey:new Uint8Array(16).fill(99),sessionId:'TEST_ONLY_SESSION'}) !== await nodeProof({payloadKey:key,sessionId:'TEST_ONLY_SESSION'}))
    const wrong = matrix.decrypt(complete.privateKey,built.envelope.ciphertext,nodeId)
    check('wrong full key never keyHash-success',!(await checkRecoveredKeyHash(wrong,built.envelope)).ok)
    let signRejected = false; try {await provider.wrapForPeer('FALCON',toHex(signer.publicKey),key)} catch {signRejected=true}; check('standard SIGN key still rejected for wrapping',signRejected)
    for (const field of ['purpose','version','kind']) {const obj=JSON.parse(atob(f.publicKey));obj[field]=field === 'version'?2:'SIGN';rejected('wrong '+field+' material rejects',()=>matrix.parseMaterial(btoa(JSON.stringify(obj)),'PUBLIC'))}
    rejected('sign hex rejected as matrix public',()=>matrix.parseMaterial(toHex(signer.publicKey),'PUBLIC'))
    rejected('wrong recipient rejects',()=>matrix.decrypt(f.privateKey,f.ciphertext,'TEST_ONLY_WRONG'))
    rejected('secret PRIVATE rejected as public upload',()=>matrix.parseMaterial(f.privateKey,'PUBLIC'))
    rejected('compressed material refused without decompress',()=>matrix.parseMaterial('COMPRESSED:'+f.publicKey,'PUBLIC'))
    rejected('oversize material refused',()=>matrix.parseMaterial('A'.repeat(8000001),'PUBLIC'))
    rejected('noncanonical base64 rejected',()=>matrix.decodeCiphertext(f.ciphertext+'='))
    const raw=Uint8Array.from(atob(f.ciphertext),c=>c.charCodeAt(0))
    for(const offset of [0,5,9,13,17]) {const bad=raw.slice();bad[offset]^=1;rejected('bad ciphertext header offset '+offset,()=>matrix.decodeCiphertext(matrix.encodeB64(bad)))}
    rejected('truncated ciphertext rejects',()=>matrix.decodeCiphertext(matrix.encodeB64(raw.slice(0,-1))))
    rejected('trailing ciphertext rejects',()=>matrix.decodeCiphertext(matrix.encodeB64(Uint8Array.from([...raw,0]))))
    const negative=raw.slice();new DataView(negative.buffer).setBigInt64(21,-1n,true);rejected('negative matrix ciphertext entry rejects',()=>matrix.decodeCiphertext(matrix.encodeB64(negative)))
    const badParams=JSON.parse(atob(f.publicKey));badParams.parameters.m=2048;rejected('unknown material params rejects',()=>matrix.parseMaterial(btoa(JSON.stringify(badParams)),'PUBLIC'))
    check('same-prefix different full materials fingerprint distinct',f.publicKey.slice(0,64) === complete.publicKey.slice(0,64) && await matrix.materialFingerprint(f.publicKey,'PUBLIC') !== await matrix.materialFingerprint(complete.publicKey,'PUBLIC'))
    const controller=new AbortController();const operation=runFalconWorker('completePartial',[f.partial,nodeId],controller.signal);controller.abort();let cancelled=false;try{await operation}catch{cancelled=true};check('cancel terminates heavy Worker',cancelled)
    await provider.destroy(signRef);await provider.destroy(ref);await provider.destroy(generationRef)
    return {testOnly:true,checks,vectors:[{privateKey:f.privateKey,ciphertext:envelope.ciphertext,keyHex:f.keyHex},{privateKey:complete.privateKey,publicKey:complete.publicKey,ciphertext:browserCt,keyHex:f.keyHex}]}
  })()`)
  for (const check of result.checks) console.log(`[PASS] real-browser ${check}`)
  console.log(oracle('verify', JSON.stringify(result)))
  // Actual browser reload and module re-import (not Node emulation of strict mode).
  await send('Page.reload')
  await evaluate('new Promise(resolve => document.readyState === "complete" ? resolve() : addEventListener("load", resolve, {once:true}))')
  const reload = await evaluate(`(async()=>{const {decodeCiphertext}=await import('/src/utils/crypto/falcon-cl-v1.js');return decodeCiphertext(${JSON.stringify(fixture.ciphertext)}).length===3})()`)
  assert.equal(reload, true)
  console.log(`[PASS] real-browser reload + actual strict ESM module (${result.checks.length + 2} checks total)`)
} finally { ws.close(); await fetch(`${cdp}/json/close/${target.id}`).catch(()=>{}) }
