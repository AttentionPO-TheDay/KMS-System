/** Docker 镜像实际运行检查；只创建/停止本脚本的临时容器，不碰业务 DB/真实链。 */
import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { dockerBin } from './lib/mysql.mjs'

const token = 'container-offline-only-not-a-real-credential'
const docker = args => execFileSync(dockerBin, args, { encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } }).trim()
const name = `kms-fabric-check-${Date.now()}`
let container = '', passed = 0
const check = (label, ok) => { assert(ok, label); passed++; console.log(`[PASS] ${label}`) }
const headers = { 'X-Internal-Token': token }
const read = async (path, auth = true) => {
  const response = await fetch(`http://127.0.0.1:19094${path}`, { headers: auth ? headers : {}, signal: AbortSignal.timeout(5000) })
  return { status: response.status, body: await response.json() }
}
try {
  container = docker(['run', '--rm', '-d', '--name', name, '-p', '127.0.0.1:19094:9094',
    '-e', 'FABRIC_DID_HOST=0.0.0.0', '-e', 'FABRIC_DID_PORT=9094',
    '-e', 'KMS_CHAIN_WRITES_ENABLED=false',
    '-e', 'FABRIC_DID_ENABLED=true', '-e', 'FABRIC_DID_WRITE_ENABLED=true',
    '-e', 'FABRIC_DID_CREATE_POLICY_APPROVED=false', '-e', 'FABRIC_DID_CHAIN_ID=',
    '-e', 'FABRIC_DID_METHOD_ID=', '-e', 'FABRIC_DID_PROPERTIES_FILE=',
    '-e', 'FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE=', '-e', `INTERNAL_TOKEN=${token}`, 'kms-fabric-did:local'])
  let health
  for (let tries = 0; tries < 50 && !health; tries++) {
    try { health = await read('/health', false) }
    catch { await new Promise(resolve => setTimeout(resolve, 100)) }
  }
  check('镜像 JVM 启动，缺配置不加载真实链 SDK', health?.status === 200 && health.body.data.status === 'NOT_CONFIGURED')
  const unauthorized = await read('/internal/fabric-did/status', false)
  check('容器内部入口拒绝无凭据请求', unauthorized.status === 401)
  const status = await read('/internal/fabric-did/status')
  check('容器状态明确未配置/禁止写入/网络未验证', status.status === 200 && status.body.data.status === 'NOT_CONFIGURED'
    && status.body.data.writeEnabled === false && status.body.data.capabilities.networkChecked === false)
  const did = await read('/internal/fabric-did/did?did=did:offline:only-read-missing-config')
  check('容器 DID 读取不假成功或回退旧链', did.status >= 400 && did.body.data.errorCode === 'NOT_CONFIGURED')
  check('全局暂停独立于 Fabric 写开关', status.body.data.chainWriteState === 'PAUSED')
  for (const action of ['prepare', 'submit']) {
    const response = await fetch(`http://127.0.0.1:19094/internal/fabric-did/bindings/${action}`, {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(5000)
    })
    const body = await response.json()
    check(`全局暂停拒绝 DID ${action} 且不生成交易`, response.status >= 400 && body.data.errorCode === 'CHAIN_WRITES_PAUSED')
  }
  const version = spawnSync(dockerBin, ['exec', container, 'java', '-version'], { encoding: 'utf8' })
  check('镜像使用独立 Java 8 运行时', version.status === 0 && /1\.8\.0/.test((version.stdout || '') + (version.stderr || '')))
  console.log(`Docker 离线 Bridge ${passed}/${passed} 项通过；没有提供真实 Fabric 身份。`)
} finally {
  if (container) docker(['stop', container])
}
