#!/usr/bin/env node
// Isolated Docker network + dummy HTTP backend. No production request/DB access.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const suffix = crypto.randomUUID().slice(0, 8)
const network = `kms-probe-test-${suffix}`
const backend = `kms-probe-backend-${suffix}`
const gateway = `kms-probe-gateway-${suffix}`
const root = new URL('../../../', import.meta.url)
const output = new URL('kms-ops/tests/out-distribution-sidechannel/', root)
const config = new URL(`dummy-${suffix}.conf`, output)
function docker(...args) { return execFileSync('docker', args, { encoding: 'utf8', timeout: 30000, maxBuffer: 512 * 1024, env: { ...process.env, MSYS_NO_PATHCONV: '1' }, stdio: ['ignore', 'pipe', 'pipe'] }).trim() }
let networkCreated = false; let backendCreated = false; let gatewayCreated = false
await mkdir(output, { recursive: true })
await writeFile(config, 'events {}\nhttp { server { listen 8000; listen 9081; listen 9082; listen 9090; location / { default_type application/json; return 200 \'{"code":200,"testOnly":true}\'; } } }\n')
try {
  docker('network', 'create', network); networkCreated = true
  docker('run', '-d', '--name', backend, '--network', network,
    '--network-alias', 'dvadmin3-django', '--network-alias', 'generate-java', '--network-alias', 'updatedel-java', '--network-alias', 'acceptance-backend',
    '--mount', `type=bind,source=${fileURLToPath(config)},target=/tmp/probe.conf,readonly`,
    '--entrypoint', 'nginx', 'kms-gateway-nginx:local', '-c', '/tmp/probe.conf', '-g', 'daemon off;'); backendCreated = true
  docker('run', '-d', '--name', gateway, '--network', network, '-p', '127.0.0.1::80', '-p', '127.0.0.1::8088',
    '-e', 'KMS_DEMO_ENABLED=true', '-e', 'INTERNAL_TOKEN=TEST_ONLY_DUMMY_GATEWAY_TOKEN',
    '--mount', `type=bind,source=${fileURLToPath(new URL('kms-ops/nginx/nginx.conf', root))},target=/etc/nginx/nginx.conf,readonly`,
    '--mount', `type=bind,source=${fileURLToPath(new URL('kms-ops/nginx/demo-server.conf.template', root))},target=/etc/nginx/kms-demo.template,readonly`,
    'kms-gateway-nginx:local'); gatewayCreated = true
  const origin = port => `http://${docker('port', gateway, `${port}/tcp`)}`
  const main = origin(80); const demo = origin(8088)
  for (let i = 0; i < 50; i++) {
    try { const response = await fetch(`${main}/ping`, { signal: AbortSignal.timeout(1000) }); if (response.ok) break } catch {}
    if (i === 49) throw new Error('Temporary gateway did not start')
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  docker('exec', gateway, 'nginx', '-t')
  async function burst(base, path, method = 'POST') {
    return Promise.all(Array.from({ length: 100 }, async () => {
      const response = await fetch(base + path, { method, signal: AbortSignal.timeout(10000) })
      await response.arrayBuffer()
      return response.status
    }))
  }
  const cases = [
    [main, '/pqkds-api/pqkds/node-self/envelopes/1/verify/'],
    [main, '/pqkds-api/node-self/envelopes/1/recover/'],
    [main, '/pqkds-api/pqkds/node-self/sessions/TEST_ONLY/confirm/'],
    [demo, '/demo-api/pqkds/node-self/envelopes/1/sign/']
  ]
  for (const [base, path] of cases) {
    const statuses = await burst(base, path)
    assert.ok(statuses.includes(429), `No rate limit on ${path}`)
    assert.ok(statuses.every(status => status === 200 || status === 429), `Unexpected upstream error on ${path}`)
    console.log(`[PASS] ${path}: ${statuses.filter(s => s === 429).length}/100 limited`)
  }
  const polling = await burst(main, '/pqkds-api/pqkds/node-self/sessions/', 'GET')
  assert.ok(polling.every(status => status === 200), 'GET polling must bypass this limiter')
  const unrelated = await burst(main, '/pqkds-api/pqkds/node-self/profile/')
  assert.ok(unrelated.every(status => status === 200), 'Unrelated API must bypass this limiter')
  console.log('[PASS] GET polling and unrelated POST bypass the crypto probe limiter')
} finally {
  if (gatewayCreated) docker('rm', '-f', gateway)
  if (backendCreated) docker('rm', '-f', backend)
  if (networkCreated) docker('network', 'rm', network)
}
