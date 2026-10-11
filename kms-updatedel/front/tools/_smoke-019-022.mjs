// 临时冒烟：KMS-019/022 新端点存活 + 路径不冲突（用完即删）
import { login } from '../../../tools/lib/captcha.mjs'

const ORIGIN = 'http://127.0.0.1'
const token = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
const call = async (path, opts = {}) => {
  const res = await fetch(ORIGIN + path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    ...(opts.body ? { body: JSON.stringify(opts.body) } : {})
  })
  return { status: res.status, body: await res.json().catch(() => null) }
}
const B = '/lifecycle-api'
console.log('runs:', JSON.stringify(await call(`${B}/lifecycle/auto-update/runs`)).slice(0, 260))
console.log('latest:', JSON.stringify(await call(`${B}/lifecycle/auto-update/latest?keyIds=1,2`)).slice(0, 260))
console.log('scans:', JSON.stringify(await call(`${B}/lifecycle/keymanage/health/scans`)).slice(0, 260))
console.log('single health/4:', JSON.stringify(await call(`${B}/lifecycle/keymanage/health/4`)).slice(0, 200))
console.log('run-once:', JSON.stringify(await call(`${B}/lifecycle/auto-update/run-once`, { method: 'POST' })).slice(0, 400))
console.log('scan:', JSON.stringify(await call(`${B}/lifecycle/keymanage/health/scan`, { method: 'POST' })).slice(0, 400))
console.log('scans after:', JSON.stringify(await call(`${B}/lifecycle/keymanage/health/scans`)).slice(0, 400))
