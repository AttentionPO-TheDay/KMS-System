// TEST ONLY. Real HTTP + docker/MySQL fixtures; never import this from product code.
// All mutations require an explicitly authorized isolated local stack. No Python.
import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { setTimeout as delay } from 'node:timers/promises'
import { login } from '../../../tools/lib/captcha.mjs'
import { dockerBin } from '../../../tools/lib/mysql.mjs'
import { SM2 } from 'gm-crypto'
import { isValidPublicKey } from '../src/utils/sm2-envelope.js'

export const config = {
  origin: process.env.KMS_VERIFY_ORIGIN || 'http://127.0.0.1',
  apiBase: process.env.KMS_VERIFY_API_BASE || '/lifecycle-api',
  loginBase: process.env.KMS_VERIFY_LOGIN_BASE || '/updatedel-api',
  mysql: process.env.KMS_MYSQL_CONTAINER || 'kms_mysql',
  java: process.env.KMS_VERIFY_JAVA_CONTAINER || 'kms_updatedel_java',
  cdp: process.env.KMS_VERIFY_CDP || 'http://127.0.0.1:9222',
  browser: process.env.KMS_VERIFY_BROWSER || 'optional',
  uiBase: process.env.KMS_VERIFY_UI_BASE || '/updatedel',
  timeout: Number(process.env.KMS_VERIFY_HTTP_TIMEOUT_MS || 120000),
  role: Number(process.env.KMS_VERIFY_ROLE_ID || 2),
  dept: Number(process.env.KMS_VERIFY_DEPT_ID || 103)
}
const hidden = new Set()
export function secret(value) { if (value) hidden.add(String(value)); return value }
export function redact(value) {
  let text = String(value ?? '')
  for (const value of hidden) text = text.split(value).join('[REDACTED]')
  return text.replace(/Bearer\s+\S+/gi, 'Bearer [REDACTED]')
    .replace(/(?:token|password|secret)\s*[=:]\s*[^\s,;]+/gi, '[REDACTED]')
    .replace(/[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[REDACTED]')
    .slice(0, 700)
}
export function reporter(name) {
  const results = []
  return {
    check(label, pass, detail = '') {
      results.push({ label, state: pass ? 'PASS' : 'FAIL' })
      console.log(`[${pass ? 'PASS' : 'FAIL'}] ${label}${detail ? ` -> ${redact(detail)}` : ''}`)
      return Boolean(pass)
    },
    skip(label, reason) {
      results.push({ label, state: 'UNAVAILABLE' })
      console.log(`[UNAVAILABLE] ${label} -> ${redact(reason)}`)
    },
    info(value) { console.log(`[info] ${redact(value)}`) },
    finish() {
      const count = state => results.filter(row => row.state === state).length
      console.log(`\n${name}: ${count('PASS')} passed, ${count('FAIL')} failed, ${count('UNAVAILABLE')} unavailable`)
      // Missing browser evidence is PARTIAL, never a complete acceptance PASS.
      process.exitCode = count('FAIL') ? 1 : count('UNAVAILABLE') ? 2 : 0
    }
  }
}
export function requireThat(condition, reason) { if (!condition) throw new Error(reason) }
export const quote = value => value == null ? 'NULL' : `CONVERT(0x${Buffer.from(String(value)).toString('hex')} USING utf8mb4)`
export const number = value => {
  const result = Number(value)
  requireThat(Number.isSafeInteger(result) && result >= 0, 'Invalid numeric fixture identifier')
  return result
}
// Avoid the legacy SQL helper's shell interpolation and error echo (queries may contain material).
// Password stays inside the container shell; only SQL is supplied on stdin, never command args.
export function sql(query) {
  try {
    return execFileSync(dockerBin, ['exec', '-i', config.mysql, 'sh', '-c',
      'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 --batch --raw --skip-column-names'],
    { input: query, encoding: 'utf8', timeout: 60000, stdio: ['pipe', 'pipe', 'pipe'] }).trim()
  } catch (error) {
    const message = String(error.stderr || '').split('\n').filter(line => /ERROR \d+/.test(line)).join('\n')
    // Do not print the SQL or child-process command, even on failure.
    throw new Error(`MySQL command failed (${config.mysql}): ${redact(message || 'docker/container connectivity or client failure')}`)
  }
}
export function rows(query) { return sql(query).split('\n').filter(Boolean).map(line => JSON.parse(line)) }
export function scalar(query) { return sql(query).split('\n')[0] || null }
export async function http(token, path, { method = 'GET', body, base = config.apiBase } = {}) {
  const response = await fetch(`${config.origin}${base}${path}`, {
    method, signal: AbortSignal.timeout(config.timeout),
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {})
  })
  return { status: response.status, body: await response.json().catch(() => null) }
}
export const ok = response => response.status >= 200 && response.status < 300 && response.body?.code === 200
export function mustOk(response, label) {
  requireThat(ok(response), `${label}: HTTP ${response.status}, code ${response.body?.code ?? 'non-JSON'}; ${redact(response.body?.msg || '')}`)
  return response.body
}
export const denied = response => response.status !== 404 && response.status !== 405
  && (response.status === 401 || response.status === 403 || (response.status === 200 && response.body?.code !== 200 && /无权|权限|管理员|他人/.test(response.body?.msg || '')))
export async function authenticate(username, password) {
  secret(password)
  try {
    return secret(await login(config.origin, config.loginBase, username, password,
      { signal: AbortSignal.timeout(config.timeout), timeoutMs: config.timeout }))
  } catch { throw new Error(`Login failed via ${config.loginBase}; check credentials, captcha/Redis configuration and stack connectivity (response suppressed)` ) }
}
export function authorizeMutation() {
  const url = new URL(config.origin)
  requireThat(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'Refusing non-loopback verifier origin')
  requireThat(process.env.KMS_VERIFY_MUTATION === 'fixtures-only',
    'No writes authorized. After user approval of an ISOLATED stack set KMS_VERIFY_MUTATION=fixtures-only')
  requireThat(process.env.KMS_VERIFY_ISOLATED_STACK === 'yes',
    'Refusing shared-stack writes. KMS_VERIFY_ISOLATED_STACK=yes acknowledges a throwaway local app/DB/Redis stack')
  requireThat(Number.isFinite(config.timeout) && config.timeout > 0, 'HTTP timeout must be positive')
  requireThat(['off', 'optional', 'required'].includes(config.browser), 'KMS_VERIFY_BROWSER must be off, optional or required')
}
// Real SM2 curve point from the repository's gm-crypto test dependency, not a bogus '04' placeholder.
export function publicUa() {
  const pair = SM2.generateKeyPair()
  const ua = pair.publicKey.toLowerCase()
  requireThat(isValidPublicKey(ua), 'Generated SM2 fixture uA is not a valid sm2p256v1 point')
  // Only the PUBLIC half escapes. No private material is output or persisted.
  pair.privateKey = ''
  return ua
}

export class Fixtures {
  constructor(prefix, report) {
    this.tag = `${prefix}-${Date.now().toString(36)}-${randomBytes(3).toString('hex')}`
    this.report = report
    this.users = []
    this.keys = []
    this.autoRuns = new Set()
    this.healthRuns = new Set()
  }
  async prepare() {
    authorizeMutation()
    this.report.info(`TAG=${this.tag}; API=${config.origin}${config.apiBase}; DB container=${config.mysql}`)
    this.admin = await authenticate(process.env.KMS_VERIFY_ADMIN_USER || 'admin',
      process.env.KMS_VERIFY_ADMIN_PASSWORD || 'admin123')
    const identity = mustOk(await http(this.admin, '/getInfo', { base: config.loginBase }), 'admin identity')
    requireThat(Number(identity.user?.userId) === 1 || identity.roles?.includes('admin'), 'Real platform admin required; demo projection is not a fixture administrator')
    requireThat(scalar(`SELECT COUNT(*) FROM kms.sys_role WHERE role_id=${number(config.role)} AND role_key<>'admin' AND status='0';`) === '1',
      'Fixture role must be an existing enabled ordinary (non-admin) role')
    for (const suffix of ['owner', 'foreign']) {
      const user = { name: `${this.tag}-${suffix}`, password: secret(`Vf!${randomBytes(12).toString('hex')}`) }
      this.users.push(user) // Register exact username before create, for partial-failure cleanup.
      mustOk(await http(this.admin, '/system/user', { base: config.loginBase, method: 'POST', body: {
        userName: user.name, nickName: user.name, password: user.password, status: '0',
        deptId: config.dept, roleIds: [config.role], postIds: [], roleLevel: 2, principalType: 'USER'
      } }), 'create isolated ordinary user')
      user.id = number(scalar(`SELECT user_id FROM kms.sys_user WHERE user_name=${quote(user.name)};`))
      requireThat(user.id > 1, 'Ordinary fixture must not be admin')
      user.token = await authenticate(user.name, user.password)
      const info = mustOk(await http(user.token, '/getInfo', { base: config.loginBase }), 'ordinary identity')
      requireThat(number(info.user?.userId) === user.id && !info.roles?.includes('admin'), 'Fixture login must preserve ordinary identity')
    }
    ;[this.owner, this.foreign] = this.users
  }
  seedKey(label, { owner = this.owner, algorithm = 'SM2', ua = publicUa(), value = 'TEST_ONLY_NOT_PRODUCTION_MATERIAL', auto = '0', due = false } = {}) {
    const name = `${this.tag}-${label}`
    // Every row is registered before write; cleanup always joins exact name AND fixture owner.
    const key = { name, owner, algorithm }
    this.keys.push(key)
    sql(`INSERT INTO kms.keymanage (user_id,user_name,encryt_type,encryt_name,key_name,key_use,key_value,cre_time,upd_time,auto_update,status,version,ua,key_domain,key_material_state)
      VALUES (${owner.id},${quote(owner.name)},${quote('非对称')},${quote(algorithm)},${quote(name)},${quote(this.tag)},${quote(value)},DATE_FORMAT(NOW(),'%Y-%m-%d %H:%i:%s'),
      ${due ? "'2000-01-01 00:00:00'" : "DATE_FORMAT(NOW(),'%Y-%m-%d %H:%i:%s')"},${quote(auto)},'0',1,${quote(ua)},${quote(this.tag)},'active');`)
    key.id = number(scalar(`SELECT key_id FROM kms.keymanage WHERE key_name=${quote(name)} AND user_id=${owner.id};`))
    requireThat(key.id > 0, 'Fixture key not found after insert')
    return key
  }
  keyWhere() {
    return this.keys.length ? this.keys.map(key => `(key_name=${quote(key.name)} AND user_id=${key.owner.id})`).join(' OR ') : 'FALSE'
  }
  assertGlobalAutoSafe() {
    const foreign = number(scalar(`SELECT COUNT(*) FROM kms.keymanage WHERE auto_update='1' AND status<>'3' AND NOT (${this.keyWhere()});`))
    // Check ALL enabled non-fixtures, not only currently due: another key may become due while waiting.
    requireThat(foreign === 0, `Unsafe global run-once: ${foreign} enabled non-fixture keys; refuse instead of changing anybody else's keys`)
  }
  async cleanup() {
    const names = this.users.map(user => quote(user.name)).join(',') || "''"
    // Build exact IDs from rows we own; never LIKE, never global DELETE.
    const ids = rows(`SELECT JSON_OBJECT('id',key_id) FROM kms.keymanage WHERE ${this.keyWhere()};`).map(row => number(row.id))
    if (ids.length) {
      const list = ids.join(',')
      // Own scheduled run with only own items may be removed; shared/empty scheduler runs are not ours.
      const ownRuns = rows(`SELECT DISTINCT JSON_OBJECT('id',i.run_id) FROM kms.kms_auto_update_item i WHERE i.key_id IN (${list})
        AND NOT EXISTS (SELECT 1 FROM kms.kms_auto_update_item x WHERE x.run_id=i.run_id AND x.key_id NOT IN (${list}));`)
      for (const run of ownRuns) this.autoRuns.add(run.id)
      sql(`START TRANSACTION;
        DELETE FROM kms.kms_auto_update_item WHERE key_id IN (${list});
        DELETE FROM kms.key_health_scan_item WHERE key_id IN (${list});
        DELETE FROM kms.key_operation_record WHERE key_id IN (${list});
        DELETE FROM kms.keymanage_version_history WHERE key_id IN (${list});
        DELETE FROM kms.keymanage WHERE key_id IN (${list}) AND (${this.keyWhere()}); COMMIT;`)
    }
    for (const id of this.autoRuns) {
      sql(`DELETE FROM kms.kms_auto_update_run WHERE run_id=${quote(id)} AND NOT EXISTS
        (SELECT 1 FROM kms.kms_auto_update_item WHERE run_id=${quote(id)});`)
    }
    for (const id of this.healthRuns) {
      sql(`DELETE FROM kms.key_health_scan_run WHERE run_id=${quote(id)} AND NOT EXISTS
        (SELECT 1 FROM kms.key_health_scan_item WHERE run_id=${quote(id)});`)
    }
    // API login/audit rows also belong to these random usernames; no token-store global flush.
    sql(`START TRANSACTION;
      DELETE ur FROM kms.sys_user_role ur JOIN kms.sys_user u ON u.user_id=ur.user_id WHERE u.user_name IN (${names});
      DELETE up FROM kms.sys_user_post up JOIN kms.sys_user u ON u.user_id=up.user_id WHERE u.user_name IN (${names});
      DELETE FROM kms.sys_logininfor WHERE user_name IN (${names});
      DELETE FROM kms.sys_oper_log WHERE oper_name IN (${names});
      DELETE FROM kms.sys_user WHERE user_name IN (${names}); COMMIT;`)
    this.report.check('Cleanup removed only exact TAG keys/users',
      scalar(`SELECT COUNT(*) FROM kms.keymanage WHERE ${this.keyWhere()};`) === '0'
      && scalar(`SELECT COUNT(*) FROM kms.sys_user WHERE user_name IN (${names});`) === '0')
    // Logout only tokens minted by this verifier (Redis TTL is fallback on network failure).
    for (const user of this.users) if (user.token) {
      try { await http(user.token, '/logout', { base: config.loginBase, method: 'POST' }) }
      catch { this.report.info('Fixture login token logout unavailable; its normal Redis TTL remains') }
    }
    if (this.admin) {
      try { await http(this.admin, '/logout', { base: config.loginBase, method: 'POST' }) } catch { /* TTL */ }
    }
  }
}

export function runtimeAutoSettings() {
  let inspected
  try { inspected = JSON.parse(execFileSync(dockerBin, ['inspect', config.java], { encoding: 'utf8', timeout: 10000 }))[0] }
  catch { throw new Error('Cannot inspect Java container runtime configuration; refusing global auto-update') }
  const env = Object.fromEntries((inspected.Config?.Env || []).map(entry => {
    const at = entry.indexOf('='); return [entry.slice(0, at), entry.slice(at + 1)]
  }))
  // Unknown overrides can change cutoff/window; do not pretend repository defaults are runtime facts.
  requireThat(!env.SPRING_APPLICATION_JSON && !env.JAVA_TOOL_OPTIONS && !env.JDK_JAVA_OPTIONS,
    'Runtime has generic Java/Spring overrides; use a dedicated isolated stack with explicit lifecycle env settings')
  requireThat(!(inspected.Config?.Cmd || []).some(arg => /auto-update|spring.config/.test(arg)), 'Unverified command-line lifecycle overrides; refusing')
  const interval = Number(env.KMS_LIFECYCLE_AUTO_UPDATE_INTERVAL_MINUTES)
  const scan = Number(env.KMS_LIFECYCLE_AUTO_UPDATE_SCAN_DELAY_MS)
  requireThat(Number.isFinite(interval) && interval > 0 && Number.isFinite(scan) && scan >= 1000,
    'Explicit positive runtime KMS_LIFECYCLE_AUTO_UPDATE_INTERVAL_MINUTES/SCAN_DELAY_MS required')
  return { interval, scan }
}
export async function waitForScheduledWindows(fixtures, afterRun, settings, report) {
  const budget = Number(process.env.KMS_VERIFY_WINDOW_WAIT_MS || settings.scan * 2 + 30000)
  const poll = Number(process.env.KMS_VERIFY_POLL_MS || 1000)
  requireThat(Number.isFinite(budget) && budget >= settings.scan * 2 && Number.isFinite(poll) && poll >= 100, 'Window wait must cover >=2 configured scan delays; poll >=100ms')
  requireThat(budget + 120000 < settings.interval * 60000, 'Two-window wait plus test margin must fit inside the failure backoff interval')
  report.info(`Waiting for two real SCHEDULED finished runs (delay=${settings.scan}ms, budget=${budget}ms); not substituting manual reruns`)
  const deadline = Date.now() + budget
  let windows = []
  while (Date.now() < deadline) {
    fixtures.assertGlobalAutoSafe()
    windows = rows(`SELECT JSON_OBJECT('id',run_id,'candidate',candidate_count,'success',success_count,'fail',fail_count,'skipped',skipped_count)
      FROM kms.kms_auto_update_run WHERE trigger_source='SCHEDULED' AND finished_at IS NOT NULL
      AND started_at > (SELECT finished_at FROM kms.kms_auto_update_run WHERE run_id=${quote(afterRun)}) ORDER BY started_at,run_id;`)
    if (windows.length >= 2) break
    await delay(poll)
  }
  requireThat(windows.length >= 2, 'Two scheduled scan windows were not observed before deadline; scheduler/backoff evidence unavailable')
  for (const [index, run] of windows.slice(0, 2).entries()) {
    report.check(`Scheduled window ${index + 1} has no duplicate fixture candidates`, run.candidate === 0 && run.success === 0 && run.fail === 0 && run.skipped === 2,
      `candidates=${run.candidate} success=${run.success} fail=${run.fail} skipped=${run.skipped}`)
  }
}

class Cdp {
  constructor(socket) {
    this.socket = socket; this.pending = new Map(); this.next = 0
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data)
      const pending = this.pending.get(message.id)
      if (pending) { this.pending.delete(message.id); clearTimeout(pending.timer); message.error ? pending.reject(new Error('CDP request rejected')) : pending.resolve(message.result) }
    })
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new Error('CDP disconnected')) }
      this.pending.clear()
    })
  }
  static async connect(url) {
    const socket = new WebSocket(url)
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { socket.close(); reject(new Error('CDP connect timeout')) }, 10000)
      socket.addEventListener('open', () => { clearTimeout(timer); resolve() }, { once: true })
      socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP connect failed')) }, { once: true })
    })
    return new Cdp(socket)
  }
  rpc(method, params = {}) {
    const id = ++this.next
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`CDP ${method} timeout`)) }, 20000)
      this.pending.set(id, { resolve, reject, timer }); this.socket.send(JSON.stringify({ id, method, params }))
    })
  }
  async evaluate(expression) {
    const reply = await this.rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    requireThat(!reply.exceptionDetails, 'Browser evaluation failed (exception suppressed to protect credentials)')
    return reply.result?.value
  }
  async wait(expression, timeout = 25000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) { if (await this.evaluate(expression)) return; await delay(250) }
    throw new Error('Browser DOM condition did not become true before deadline')
  }
  async navigate(url) {
    // Repository harness observes Page.navigate occasionally hanging; do not await its response.
    this.rpc('Page.navigate', { url }).catch(() => {})
    await this.wait('document.readyState === "complete"')
  }
  close() { this.socket.close() }
}
// Fresh incognito context: never overwrite cookies/local storage in anybody's open browser tab.
export async function browserChecks(fixtures, label, callback) {
  const report = fixtures.report
  if (config.browser === 'off') { report.skip(label, 'KMS_VERIFY_BROWSER=off; UI checks NOT passed'); return }
  let version
  try {
    const endpoint = new URL(config.cdp)
    requireThat(['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname), 'CDP endpoint must be loopback')
    version = await (await fetch(`${config.cdp}/json/version`, { signal: AbortSignal.timeout(3000) })).json()
  } catch {
    if (config.browser === 'required') throw new Error('Required repository CDP browser endpoint unavailable')
    report.skip(label, 'Repository CDP browser unavailable; API/DB evidence does not prove UI'); return
  }
  let root, page, context
  try {
    root = await Cdp.connect(version.webSocketDebuggerUrl)
    context = (await root.rpc('Target.createBrowserContext')).browserContextId
    const target = await root.rpc('Target.createTarget', { url: `${config.origin}${config.uiBase}/login`, browserContextId: context })
    const targets = await (await fetch(`${config.cdp}/json/list`, { signal: AbortSignal.timeout(3000) })).json()
    const tab = targets.find(value => value.id === target.targetId)
    requireThat(tab?.webSocketDebuggerUrl, 'Fresh browser target not listed')
    page = await Cdp.connect(tab.webSocketDebuggerUrl)
    await page.rpc('Page.enable'); await page.rpc('Runtime.enable')
    await page.wait(`location.origin === ${JSON.stringify(config.origin)} && document.readyState === 'complete'`)
    await page.evaluate(`document.cookie = ${JSON.stringify(`Admin-Token=${fixtures.admin}; path=/`)}; true`)
    await callback(page)
  } finally {
    page?.close()
    if (root && context) await root.rpc('Target.disposeBrowserContext', { browserContextId: context }).catch(() => {})
    root?.close()
  }
}
export function help(name) {
  if (!process.argv.includes('--help')) return false
  console.log(`${name}: real local Java lifecycle API/DB/UI verification. No writes without KMS_VERIFY_MUTATION=fixtures-only and KMS_VERIFY_ISOLATED_STACK=yes.\nOptions: KMS_VERIFY_ORIGIN, KMS_VERIFY_API_BASE (/lifecycle-api), KMS_VERIFY_LOGIN_BASE (/updatedel-api), KMS_MYSQL_CONTAINER, KMS_REDIS_CONTAINER, KMS_VERIFY_JAVA_CONTAINER, DOCKER_BIN, KMS_VERIFY_ADMIN_USER/PASSWORD, KMS_VERIFY_ROLE_ID/DEPT_ID, KMS_VERIFY_CDP, KMS_VERIFY_BROWSER (off|optional|required), KMS_VERIFY_UI_BASE, KMS_VERIFY_HTTP_TIMEOUT_MS, KMS_VERIFY_WINDOW_WAIT_MS/POLL_MS.\nExit: 0=all available checks passed; 1=failure/refusal; 2=partial (browser unavailable). See .omc/research/lane-b-runtime-tests.md.`)
  return true
}
