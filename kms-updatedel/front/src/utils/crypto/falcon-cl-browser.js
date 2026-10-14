import { publicGeneration, publicGenerationContext, generationScheme } from './generation-scheme.js'

export function runFalconWorker(operation, args, signal) {
  if (signal?.aborted) return Promise.reject(new Error('Falcon CL operation cancelled'))
  // No main-thread fallback: heavy secret operations must not block revision/cancel handling.
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./falcon-cl-worker.js', import.meta.url), { type: 'module' })
    const cleanup = () => { worker.terminate(); signal?.removeEventListener('abort', abort) }
    const abort = () => { cleanup(); reject(new Error('Falcon CL operation cancelled')) }
    signal?.addEventListener('abort', abort, { once: true })
    worker.onmessage = ({ data }) => { cleanup(); data.error ? reject(new Error(data.error)) : resolve(data.result) }
    worker.onerror = () => { cleanup(); reject(new Error('Falcon CL worker failed')) }
    worker.postMessage({ operation, args })
  })
}

export async function issueFalconPartial(request, issueKeygen, expected, signal) {
  const scheme = generationScheme('FALCON_CL_V1')
  const fields = ['nodeId', 'userId', 'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision']
  if (typeof issueKeygen !== 'function' || !expected || fields.some(f => !Object.hasOwn(expected, f))) throw new Error('Falcon CL requires authenticated partial issuance and complete trusted identity')
  let issuance
  try {
    issuance = await issueKeygen({ ...request, generationScheme: scheme.schemeId, purpose: 'ENCRYPT' })
    if (signal?.aborted) throw new Error('Falcon CL operation cancelled')
    const context = publicGenerationContext(issuance?.context)
    const generation = publicGeneration({ schemeId: issuance.generationScheme, schemeVersion: 1, generationIssuanceId: issuance.generationIssuanceId, authorizationTicketId: issuance.authorizationTicketId })
    const required = { ...expected, coreFamily: 'FALCON_CL_V1', schemeId: scheme.schemeId, schemeVersion: '1', purpose: 'ENCRYPT', variant: '512', nodeId: request.nodeId, keyId: request.keyId, keyVersion: String(request.keyVersion), generationIssuanceId: generation.generationIssuanceId }
    for (const [field, value] of Object.entries(required)) if (context[field] !== String(value)) throw new Error('Falcon CL issuance identity/revision mismatch')
    if (typeof issuance.expiresAt !== 'string' || !/(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(issuance.expiresAt) || !(Date.parse(issuance.expiresAt) > Date.now()) || Object.hasOwn(issuance, 'share')) throw new Error('Falcon CL partial issuance contract invalid')
    const material = await runFalconWorker('completePartial', [issuance.partialMaterial, request.nodeId], signal)
    return { ...material, generation, generationContext: context }
  } finally {
    if (issuance) { try { delete issuance.partialMaterial } catch { /* Immutable strings cannot be erased. */ } }
  }
}
