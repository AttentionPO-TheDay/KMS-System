// =============================================================================
// tools/lib/mysql.mjs —— 验证脚本查库的统一入口
// -----------------------------------------------------------------------------
// 存在的理由：这些脚本里 `execSync('docker exec kms_mysql mysql ...')` 的写法
// 在 Windows 上**一直静默失败**，而且在两个层次上：
//
//   1. **Node 的 execSync 走 cmd.exe**，而 `docker` 只在 Git Bash / PowerShell 的
//      PATH 里，不在 cmd 的 PATH 里 → "'docker' 不是内部或外部命令"。
//      所以必须用绝对路径调 docker。
//   2. 调用方往往用 `2>nul` 吞掉 stderr → 失败信息被丢弃，只剩下一个
//      "Command failed: ..." 的空壳报错，或者更糟：被当成"查询返回空"而让断言
//      悄悄走错分支。
//
// 于是统一到这里，并且**不吞 stderr**：出错就把真实原因抛出来。
//
// ⚠️ 已知仍有此问题的脚本（本次未一并改，改动面控制）：
//   verify-distribute-algorithm.mjs / verify-distribute-ui.mjs /
//   verify-falcon-pool.mjs / verify-manual-rotation.mjs
//   它们里的 sql() 在 Windows 上大概率是空结果，断言可信度存疑。
// =============================================================================
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
/** 仓库根（tools/lib → tools → repo） */
export const REPO_ROOT = join(HERE, '..', '..')

/** docker 可执行文件的绝对路径。Node 在 Windows 上走 cmd.exe，找不到 PATH 里的 docker。 */
const DOCKER_BIN =
  process.env.DOCKER_BIN || 'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe'

const MYSQL_CONTAINER = process.env.KMS_MYSQL_CONTAINER || 'kms_mysql'

/**
 * 从 kms-ops/.env 读 MySQL root 口令。
 * ⚠️ .env 在 Windows 上是 CRLF，`(.+)$` 会把行尾 \r 一起吃进去，必须 trim。
 */
function readMysqlPassword() {
  if (process.env.MYSQL_ROOT_PASSWORD) return process.env.MYSQL_ROOT_PASSWORD.trim()
  try {
    const env = readFileSync(join(REPO_ROOT, 'kms-ops', '.env'), 'utf8')
    const m = env.match(/^\s*MYSQL_ROOT_PASSWORD\s*=\s*(.+?)\s*$/m)
    if (m) return m[1].trim()
  } catch {
    /* 落到默认值 */
  }
  return 'root123456'
}

const MYSQL_PW = readMysqlPassword()

/**
 * 执行一条 SQL，返回去掉告警行后的结果文本（-N：无表头）。
 * 失败时抛出带真实 stderr 的错误，**不静默**。
 */
export function sql(query) {
  // stderr 用 pipe **捕获**而不是放行：mysql 每次都会往 stderr 打两条告警
  // （World-writable config file / Using a password on the command line），
  // 放行的话会把测试输出刷得看不清；但也不能丢 —— 失败时它才是真正的线索。
  let raw
  try {
    raw = execSync(
      `"${DOCKER_BIN}" exec ${MYSQL_CONTAINER} mysql -uroot -p${MYSQL_PW} -N -e "${query}"`,
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }
    )
  } catch (err) {
    // 把两条例行告警剥掉后重新抛出：否则调用方看到的 stderr 全是告警，
    // 真正的 "ERROR 1146 ... doesn't exist" 被挤到后面，等于没有线索。
    const clean = String(err.stderr || '')
      .split('\n')
      .filter((l) => l.trim() && !/insecure|World-writable/i.test(l))
      .join('\n')
      .trim()
    const e = new Error(`SQL 失败：${clean || err.message}\n  SQL: ${query}`)
    e.stderr = clean
    e.sql = query
    throw e
  }
  return raw
    .split('\n')
    .filter((l) => !/insecure|Warning/i.test(l))
    .join('\n')
    .trim()
}

/** 执行一条 SQL 并返回单个标量（首行），查不到返回 null（而不是空串）。 */
export function sqlScalar(query) {
  const v = sql(query)
  return v === '' ? null : v.split('\n')[0].trim()
}

/** docker 可执行文件路径，供需要直接调 docker 的脚本复用。 */
export const dockerBin = DOCKER_BIN
