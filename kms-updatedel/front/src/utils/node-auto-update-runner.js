/** Dependency-injected runner, also used by isolated verification. */
export function createAutoUpdateRunner(deps) {
  let busy = false
  async function tick() {
    if (busy || !deps.isLoggedIn()) return
    busy = true
    try {
      const identity = deps.identity()
      const data = await deps.getPolicies()
      const sameIdentity = () => deps.isLoggedIn() && deps.identity() === identity
      if (!sameIdentity()) return
      for (const policy of data.policies || []) {
        if (!sameIdentity()) return
        if (!policy.enabled || !policy.nextRunAt || new Date(policy.nextRunAt) > new Date(data.serverTime)) continue
        const response = await deps.claim(policy.algorithm)
        const job = response?.claim
        if (!job || !sameIdentity()) continue
        let message = ''
        try {
          await deps.rotate({
            algorithm: job.algorithm, nodeId: data.nodeId, keyId: job.keyId,
            version: job.fromVersion + 1, rotate: true,
            // Unattended tasks must never approve abandoning an issuance.
            confirmUnusedIssuance: async () => false
          })
        } catch (error) {
          message = error?.message || String(error)
        }
        if (!sameIdentity()) return
        const result = await deps.complete(job.algorithm, job.leaseToken, message)
        deps.changed(result)
      }
    } finally {
      busy = false
    }
  }
  return { tick }
}
