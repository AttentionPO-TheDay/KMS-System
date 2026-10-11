import { login } from '../../../tools/lib/captcha.mjs'
import { checkTable, runSmoke } from './lib/lifecycle-smoke.mjs'

await runSmoke('verify-auto-update-task', login, async (config, get) => {
  const page = { pageNum: 1, pageSize: 10 }
  const runs = await get('auto-update runs', '/lifecycle/auto-update/runs', page)
  checkTable('auto-update runs', runs)

  const runId = config.runId || runs.rows[0]?.runId
  if (runs.rows.length && !runId) throw new Error('Run row missing runId')
  if (runId) {
    const details = await get('auto-update run details', `/lifecycle/auto-update/runs/${encodeURIComponent(runId)}`, {
      ...page,
      ...(config.keyId ? { keyId: config.keyId } : {})
    })
    checkTable('auto-update run details', details)
  } else {
    console.log('SKIP auto-update run details: no existing runs; no run was triggered')
  }

  const keyIds = (config.keyIds || config.keyId).split(',').map(id => id.trim()).filter(Boolean)
  const latest = await get('auto-update latest', '/lifecycle/auto-update/latest',
    keyIds.length ? { keyIds: keyIds.join(',') } : {})
  if (!Array.isArray(latest.data)) throw new Error('Expected latest data array')
  console.log(`PASS auto-update latest: rows=${latest.data.length}`)
})
