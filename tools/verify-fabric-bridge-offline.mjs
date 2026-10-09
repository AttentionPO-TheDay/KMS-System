/** 实际运行独立 JVM/HTTP，但不连接 Fabric、不提供任何真实身份或配置。 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { resolve, join } from 'node:path'
import { existsSync } from 'node:fs'

const jar = resolve('kms-fabric-did/target/kms-fabric-did-1.0.0.jar')
assert(existsSync(jar), '先执行 mvn -f kms-fabric-did/pom.xml clean package')
const java = process.env.FABRIC_DID_TEST_JAVA || (process.env.JAVA_HOME ? join(process.env.JAVA_HOME, 'bin/java.exe') : 'java')
const token = 'offline-test-only-not-a-real-credential'
let passed = 0
async function request(port, path, options = {}) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, { ...options, signal: AbortSignal.timeout(10000) })
  return { status: response.status, body: await response.json() }
}
function check(label, actual) { assert(actual, label); console.log(`[PASS] ${label}`); passed++ }

for (const [enabled, port, expected] of [['false', 9391, 'DISABLED'], ['true', 9392, 'NOT_CONFIGURED']]) {
  const app = spawn(java, ['-jar', jar], { env: {
    ...process.env, FABRIC_DID_HOST: '127.0.0.1', FABRIC_DID_PORT: String(port),
    FABRIC_DID_ENABLED: enabled, FABRIC_DID_WRITE_ENABLED: 'false',
    FABRIC_DID_CREATE_POLICY_APPROVED: 'false', FABRIC_DID_CHAIN_ID: '',
    FABRIC_DID_METHOD_ID: '', FABRIC_DID_PROPERTIES_FILE: '',
    FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE: '', INTERNAL_TOKEN: token
  }, stdio: ['ignore', 'pipe', 'pipe'] })
  let output = ''
  app.stdout.on('data', bytes => { output += bytes.toString() })
  app.stderr.on('data', bytes => { output += bytes.toString() })
  try {
    await new Promise((resolveReady, reject) => {
      const timeout = setTimeout(() => { clearInterval(poll); reject(new Error('Bridge did not start: ' + output.slice(-1500))) }, 15000)
      const poll = setInterval(() => {
        if (output.includes('Fabric DID Bridge started')) { clearInterval(poll); clearTimeout(timeout); resolveReady() }
        else if (app.exitCode !== null) { clearInterval(poll); clearTimeout(timeout); reject(new Error('Bridge exited: ' + output.slice(-1500))) }
      }, 50)
    })
    const health = await request(port, '/health')
    check(`${expected}: JVM 健康不等于链已连通`, health.status === 200 && health.body.data.status === expected)
    const denied = await request(port, '/internal/fabric-did/status')
    check(`${expected}: 内部入口无认证被拒`, denied.status === 401)
    const status = await request(port, '/internal/fabric-did/status', { headers: { 'X-Internal-Token': token } })
    check(`${expected}: 配置诊断不假称网络或写入就绪`, status.status === 200 && status.body.data.status === expected
      && status.body.data.capabilities.networkChecked === false && status.body.data.writeEnabled === false)
    const read = await request(port, '/internal/fabric-did/did?did=did:offline:never-contact-a-chain', { headers: { 'X-Internal-Token': token } })
    check(`${expected}: 读取在未配置边界失败，不调用真实链`, read.status >= 400 && ['DISABLED', 'NOT_CONFIGURED'].includes(read.body.data.errorCode))
  } finally {
    app.kill()
    await new Promise(resolveExit => app.exitCode !== null ? resolveExit() : app.once('exit', resolveExit))
  }
}
console.log(`\n实际 Bridge 离线 HTTP 验证 ${passed}/${passed} 项通过；未验证真实 Fabric TLS、metadata 或交易。`)
