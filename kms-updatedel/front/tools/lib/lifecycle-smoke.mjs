import { parseArgs } from 'node:util'

export async function runSmoke(name, login, verify) {
  const args = process.argv.slice(2)
  if (args.includes('--help') || args.includes('-h')) {
    console.log(`Usage: node tools/${name}.mjs [options]
Read-only functional smoke; never triggers rotation, run-once or batch scans.

  --origin URL       Server origin (KMS_ORIGIN; default http://localhost)
  --login-base PATH  Login prefix (KMS_LOGIN_BASE; default /updatedel-api)
  --api-base PATH    Lifecycle prefix (KMS_API_BASE; default /lifecycle-api)
  --timeout-ms MS    Per-request/login timeout (KMS_TIMEOUT_MS; default 15000)
  --run-id ID        Existing run/scan for details (KMS_RUN_ID; otherwise first row)
  --key-id ID        Existing key for detail filtering/single-key health (KMS_KEY_ID)
  --key-ids IDS      Comma-separated IDs for auto-update latest only (KMS_KEY_IDS)
  --help, -h        Show help without authentication or server access

Authentication: set KMS_TOKEN, or KMS_USERNAME and KMS_PASSWORD for captcha login.
No credentials or response contents are printed. No records are created.
Example: npm run ${name.replace('verify-', 'verify:')} -- --key-id <existing-id>`)
    return
  }

  let stage = 'configuration (see --help)'
  try {
    const { values } = parseArgs({
      args,
      options: {
        origin: { type: 'string' },
        'login-base': { type: 'string' },
        'api-base': { type: 'string' },
        'timeout-ms': { type: 'string' },
        'run-id': { type: 'string' },
        'key-id': { type: 'string' },
        'key-ids': { type: 'string' }
      }
    })
    const config = {
      origin: (values.origin || process.env.KMS_ORIGIN || 'http://localhost').replace(/\/+$/, ''),
      loginBase: (values['login-base'] || process.env.KMS_LOGIN_BASE || '/updatedel-api').replace(/\/+$/, ''),
      apiBase: (values['api-base'] || process.env.KMS_API_BASE || '/lifecycle-api').replace(/\/+$/, ''),
      timeoutMs: Number(values['timeout-ms'] || process.env.KMS_TIMEOUT_MS || 15000),
      runId: (values['run-id'] || process.env.KMS_RUN_ID || '').trim(),
      keyId: (values['key-id'] || process.env.KMS_KEY_ID || '').trim(),
      keyIds: (values['key-ids'] || process.env.KMS_KEY_IDS || '').trim()
    }
    const origin = new URL(config.origin)
    if (!['http:', 'https:'].includes(origin.protocol) || origin.pathname !== '/' ||
        origin.search || origin.hash || origin.username || origin.password ||
        (config.loginBase && !config.loginBase.startsWith('/')) ||
        (config.apiBase && !config.apiBase.startsWith('/')) ||
        !Number.isInteger(config.timeoutMs) || config.timeoutMs <= 0 || config.timeoutMs > 600000) {
      throw new Error('Invalid configuration')
    }

    stage = 'authentication (set KMS_TOKEN or KMS_USERNAME/KMS_PASSWORD)'
    let token = (process.env.KMS_TOKEN || '').trim().replace(/^Bearer\s+/i, '')
    if (!token) {
      if (!process.env.KMS_USERNAME || !process.env.KMS_PASSWORD) {
        throw new Error('Missing credentials')
      }
      token = await login(config.origin, config.loginBase, process.env.KMS_USERNAME, process.env.KMS_PASSWORD, {
        signal: AbortSignal.timeout(config.timeoutMs),
        timeoutMs: config.timeoutMs
      })
    }

    const get = async (label, path, query = {}) => {
      stage = `${label} (request or response shape)`
      const url = new URL(`${config.origin}${config.apiBase}${path}`)
      url.search = new URLSearchParams(query).toString()
      const response = await fetch(url, {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
        signal: AbortSignal.timeout(config.timeoutMs)
      })
      if (!response.ok) throw new Error('HTTP request failed')
      const body = await response.json()
      if (body?.code !== 200) throw new Error('API request failed')
      return body
    }
    await verify(config, get)
  } catch {
    // Captcha/login errors can include raw responses; report only the fixed check label.
    console.error(`FAIL ${name}: ${stage}`)
    process.exitCode = 1
  }
}

export function checkTable(label, body) {
  if (!Array.isArray(body.rows) || !Number.isInteger(body.total) || body.total < body.rows.length) {
    throw new Error('Expected TableDataInfo rows and total')
  }
  console.log(`PASS ${label}: rows=${body.rows.length}, total=${body.total}`)
}
