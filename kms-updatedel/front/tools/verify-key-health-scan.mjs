import { login } from '../../../tools/lib/captcha.mjs'
import { checkTable, runSmoke } from './lib/lifecycle-smoke.mjs'

await runSmoke('verify-key-health-scan', login, async (config, get) => {
  const page = { pageNum: 1, pageSize: 10 }
  const scans = await get('key-health scans', '/lifecycle/keymanage/health/scans', page)
  checkTable('key-health scans', scans)

  const runId = config.runId || scans.rows[0]?.runId
  if (scans.rows.length && !runId) throw new Error('Scan row missing runId')
  if (runId) {
    const details = await get('key-health scan details', `/lifecycle/keymanage/health/scans/${encodeURIComponent(runId)}`, {
      ...page,
      ...(config.keyId ? { keyId: config.keyId } : {})
    })
    checkTable('key-health scan details', details)
  } else {
    console.log('SKIP key-health scan details: no existing scans; no scan was triggered')
  }

  if (config.keyId) {
    const health = await get('single-key health', `/lifecycle/keymanage/health/${encodeURIComponent(config.keyId)}`)
    if (typeof health.data?.health !== 'string' ||
        !Array.isArray(health.data.findings) || !Array.isArray(health.data.observations)) {
      throw new Error('Expected single-key health result')
    }
    console.log('PASS single-key health: health, findings and observations present')
  } else {
    console.log('SKIP single-key health: no --key-id/KMS_KEY_ID supplied')
  }
})
