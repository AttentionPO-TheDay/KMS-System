/** 默认启动配置反证；只解析 Compose，不启动/重建/清理服务或读凭据输出。 */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dockerBin } from './lib/mysql.mjs'
let passed = 0
const check = (label, value) => { assert(value, label); console.log(`[PASS] ${label}`); passed++ }
const env = { ...process.env, MSYS_NO_PATHCONV: '1',
  KMS_CHAIN_WRITES_ENABLED: 'true', KMS_CHAIN_CONSUMER_ENABLED: 'true',
  KMS_LIFECYCLE_CHAIN_SYNC_ENABLED: 'true', KMS_LIFECYCLE_CHAIN_CONSUMER_ENABLED: 'true',
  FABRIC_DID_WRITE_ENABLED: 'true', FABRIC_DID_CREATE_POLICY_APPROVED: 'true' }
for (const files of [
  ['kms-ops/docker-compose.yml'],
  ['kms-ops/docker-compose.yml', 'kms-ops/docker-compose.demo.yml'],
  ['kms-ops/docker-compose.yml', 'kms-ops/docker-compose.fabric-did.yml']
]) {
  const config = JSON.parse(execFileSync(dockerBin,
    ['compose', ...files.flatMap(file => ['-f', file]),
      ...(files.some(file => file.includes('fabric-did')) ? ['--profile', 'fabric-did'] : []),
      'config', '--format', 'json'], { encoding: 'utf8', env }))
  for (const service of ['generate-java', 'updatedel-java', 'dvadmin3-django']) {
    check(`${files.at(-1)} / ${service}: 宿主 true 不能开启默认真实链写`, config.services[service].environment.KMS_CHAIN_WRITES_ENABLED === 'false')
    check(`${service}: 默认链监听关闭`, config.services[service].environment.KMS_CHAIN_CONSUMER_ENABLED === 'false')
  }
  check('生命周期专用同步/消费也固定关闭',
    config.services['updatedel-java'].environment.KMS_LIFECYCLE_CHAIN_SYNC_ENABLED === 'false'
    && config.services['updatedel-java'].environment.KMS_LIFECYCLE_CHAIN_CONSUMER_ENABLED === 'false')
  if (config.services['fabric-did-bridge']) {
    const flags = config.services['fabric-did-bridge'].environment
    check('Fabric 可选启动同样拒绝写/策略开关覆盖',
      flags.KMS_CHAIN_WRITES_ENABLED === 'false' && flags.FABRIC_DID_WRITE_ENABLED === 'false'
      && flags.FABRIC_DID_CREATE_POLICY_APPROVED === 'false')
  }
}
const start = readFileSync('kms-ops/start.sh', 'utf8')
check('默认宿主启动不执行合约部署工具', !/^\s*bash\s+(?:["']?\.\/)?deploy-keyevidence\.sh/m.test(start))
check('默认宿主启动不调用合约账户同步函数', !/^\s*sync_contract_env_from_state\s+/m.test(start))
const rebuild = readFileSync('kms-ops/rebuild-env.sh', 'utf8')
check('业务环境重建保留历史 FISCO live 状态', !/^\s*clear_dir_with_helper\s+"\$FISCO_LIVE_(?:NODE|STATE)_DIR"/m.test(rebuild))
console.log(`\n默认不上链启动配置 ${passed}/${passed} 项通过；未提交交易、未输出敏感环境值。`)
