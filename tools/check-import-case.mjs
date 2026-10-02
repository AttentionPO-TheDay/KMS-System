// 检查所有 `@/...` import 的**大小写**是否与磁盘上的真实路径逐字符一致。
//
// 为什么需要：Windows 文件系统大小写不敏感，`@/api/pkqds/...` 会被解析到
// `pqkds/`，构建照样通过 —— 但同一份代码在 Linux（CI、Docker 构建机、
// 别人的开发机）上会 "Could not resolve"，而且报错点看起来与真正的原因无关。
// 这类问题在本机**永远不会暴露**，只能靠主动扫描。
import { readdirSync, statSync, readFileSync } from 'node:fs'
import { join, dirname, resolve, relative } from 'node:path'

const ROOT = resolve(process.argv[2] || 'src')
const EXT = ['.js', '.ts', '.vue', '.mjs', '.json']

/** 逐字符比对：把路径按段拆开，每段必须在父目录里**精确**存在 */
function exactCaseExists(absPath) {
  const parts = relative(ROOT, absPath).split(/[\\/]/).filter(Boolean)
  let cur = ROOT
  for (const part of parts) {
    let entries
    try { entries = readdirSync(cur) } catch { return false }
    if (!entries.includes(part)) return false   // ← includes 是大小写敏感的
    cur = join(cur, part)
  }
  return true
}

function tryResolve(spec, fromDir) {
  const base = resolve(fromDir, spec)
  const candidates = [base, ...EXT.map((e) => base + e), ...EXT.map((e) => join(base, 'index' + e))]
  for (const c of candidates) {
    try {
      if (!statSync(c).isFile()) continue
    } catch { continue }
    if (exactCaseExists(c)) return { ok: true, path: c }
    return { ok: false, path: c }
  }
  return { ok: false, path: null, unresolved: true }
}

const files = []
;(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p)
    else if (/\.(js|ts|vue|mjs)$/.test(name)) files.push(p)
  }
})(ROOT)

const IMPORT_RE = /(?:from|import)\s*['"](@\/[^'"]+)['"]/g

let bad = 0
for (const file of files) {
  const text = readFileSync(file, 'utf8')
  for (const m of text.matchAll(IMPORT_RE)) {
    const spec = m[1].slice(2)                    // 去掉 '@/'
    const r = tryResolve(spec, ROOT)
    if (r.ok) continue
    bad++
    const line = text.slice(0, m.index).split('\n').length
    console.log(`${relative(process.cwd(), file)}:${line}  ${m[1]}`)
    console.log(`    ${r.unresolved ? '解析不到该模块（真缺失）' : `大小写不匹配，磁盘上是：${relative(ROOT, r.path)}`}`)
  }
}

console.log(bad ? `\n>>> ${bad} 处 import 有问题（在 Linux 上会构建失败）` : '\n>>> 全部 @/ import 大小写正确')
process.exitCode = bad ? 1 : 0
