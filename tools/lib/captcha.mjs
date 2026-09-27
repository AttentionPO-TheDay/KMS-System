import { execFileSync } from 'node:child_process'

/**
 * 验证码夹具：给**自动化脚本**用，不是产品行为。
 *
 * 背景
 * ----
 * `KMS_CAPTCHA_ENABLED=true` 时登录需要图形验证码，而验收脚本没有眼睛。
 * 服务端把答案存在 Redis（key `captcha_codes:<uuid>`，见 CaptchaController），
 * 所以脚本走这条路取答案：`/captchaImage` 拿 uuid → 从 Redis 读答案 → 带 code 登录。
 *
 * 这个做法的边界要说清楚：
 *   * 它**不改变产品行为**：浏览器仍然必须真的看图填写，接口侧没有留任何后门；
 *   * 它依赖 Redis 容器可达（脚本在宿主机跑，用 `docker exec`），
 *     容器内跑的脚本（security_test.sh）走自己的 /dev/tcp 实现，见那个文件；
 *   * 开关关掉时（captchaEnabled=false）本模块原样返回空 code，脚本无需分支。
 *
 * 为什么不做成"登录接口留个内部令牌就免验证码"：那等于在认证入口开一个长期后门，
 * 而验证码本身就是为了挡暴力尝试。夹具应当只存在于测试侧。
 */

const REDIS_CONTAINER = process.env.KMS_REDIS_CONTAINER || 'kms_redis'

/**
 * 取一张验证码并从 Redis 读出答案。
 * @returns {Promise<{enabled: boolean, uuid: string, code: string}>}
 */
export async function getCaptcha(origin, base = '/lifecycle-api') {
  const res = await fetch(`${origin}${base}/captchaImage`)
  const body = await res.json().catch(() => null)
  if (!body) return { enabled: false, uuid: '', code: '' }
  if (!body.captchaEnabled) return { enabled: false, uuid: '', code: '' }
  if (!body.uuid) throw new Error('captchaImage 未返回 uuid，无法取答案')

  let answer = ''
  try {
    answer = execFileSync(
      'docker',
      ['exec', REDIS_CONTAINER, 'redis-cli', 'get', `captcha_codes:${body.uuid}`],
      { encoding: 'utf8' }
    ).trim()
  } catch (e) {
    throw new Error(
      `读取验证码答案失败（${REDIS_CONTAINER}）：${e.message}\n` +
        '  提示：脚本需要在能执行 docker 的宿主机上运行；容器内请用 security_test.sh 的实现。'
    )
  }
  if (!answer) throw new Error(`Redis 里没有 captcha_codes:${body.uuid} 的答案（可能已过期）`)

  // ⚠️ 必须剥掉外层引号：服务端用 Spring 的 RedisTemplate（JSON 序列化）写入，
  // 字符串 `18` 在 Redis 里是 `"18"`（含引号）。直接把 `"18"` 当验证码提交，
  // 服务端会判「验证码错误」—— 看起来像"答案取错了"，其实只是少剥了一层引号。
  answer = answer.replace(/^"(.*)"$/s, '$1')

  return { enabled: true, uuid: body.uuid, code: answer }
}

/** 只取登录要用的两个字段，便于直接展开进请求体 */
export async function captchaFields(origin, base = '/lifecycle-api') {
  const c = await getCaptcha(origin, base)
  return { code: c.code, uuid: c.uuid }
}

/**
 * 带验证码登录，返回 token。
 * @param {string} origin 例如 http://127.0.0.1
 * @param {string} base   登录接口前缀，例如 /lifecycle-api
 */
export async function login(origin, base, username, password) {
  const extra = await captchaFields(origin, base)
  const res = await fetch(`${origin}${base}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, ...extra })
  })
  const json = await res.json().catch(() => null)
  if (!json?.token) {
    throw new Error(`登录失败 ${username}: HTTP ${res.status} ${JSON.stringify(json)?.slice(0, 200)}`)
  }
  return json.token
}
