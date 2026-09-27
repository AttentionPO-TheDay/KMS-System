/**
 * 校验 KeyOperationRecordMapper.xml 的两条 INSERT 中「列数 == 值数」。
 *
 * 背景：该表新增 proof_path 列后，列清单加了 proof_path，
 * 但值清单漏了对应占位符，导致运行期报
 *   java.sql.SQLException: Column count doesn't match value count at row 1
 * 本脚本用于在构建后静态复核，避免再次出现此类漏配。
 *
 * 用法: node tools/verify-mapper-inserts.mjs <mapper.xml 路径>
 */
import { readFileSync } from 'node:fs'

const file = process.argv[2]
if (!file) {
  console.error('用法: node tools/verify-mapper-inserts.mjs <mapper.xml>')
  process.exit(2)
}

const xml = readFileSync(file, 'utf8')

// 取出每条 <insert>...</insert>
const inserts = [...xml.matchAll(/<insert\b[^>]*id="([^"]+)"[\s\S]*?<\/insert>/g)]
if (inserts.length === 0) {
  console.error('未找到任何 <insert> 语句')
  process.exit(1)
}

const splitTop = (s) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter((x) => x.length > 0)

let failed = 0

for (const m of inserts) {
  const id = m[1]
  const body = m[0]

  // 列清单：insert into <table> ( ... ) values
  const colMatch = body.match(/insert\s+into\s+\S+\s*\(([\s\S]*?)\)\s*values/i)
  if (!colMatch) {
    console.log(`[SKIP] ${id}: 未匹配到列清单`)
    continue
  }
  const cols = splitTop(colMatch[1])

  // 值清单：values 之后的括号组。
  // 注意：SQL 里可能有 now() 这类带括号的函数调用，若直接按括号切分会被
  // 内层括号截断。这里先把 now() 归一化为一个无括号的占位记号再计数。
  const afterValues = body.slice(body.toLowerCase().indexOf('values') + 6)
  const normalized = afterValues.replace(/now\s*\(\s*\)/gi, 'NOW_FN')
  const valGroups = [...normalized.matchAll(/\(([\s\S]*?)\)/g)]
  if (valGroups.length === 0) {
    console.log(`[SKIP] ${id}: 未匹配到值清单`)
    continue
  }

  let ok = true
  // 只校验第一组值。批量插入的 <foreach> 会把同一组括号重复展开，
  // 正则可能匹配到 <foreach> 的属性括号等非值内容，那属于误报，
  // 真正的值模板只有一份。
  for (let i = 0; i < 1; i++) {
    const vals = splitTop(valGroups[i][1]).map((v) => v.replace(/^NOW_FN$/, 'now()'))
    const match = cols.length === vals.length
    if (!match) ok = false
    console.log(
      `[${match ? 'OK' : 'FAIL'}] ${id}: 列 ${cols.length} / 值 ${vals.length}`
    )
    if (!match) {
      // 指出第一个错位位置，便于定位
      const n = Math.min(cols.length, vals.length)
      for (let k = 0; k < n; k++) {
        const c = cols[k]
        const v = vals[k]
        // 列 a_b 期望值形如 #{aB} 或 #{item.aB}
        const camel = c.replace(/_([a-z])/g, (_, ch) => ch.toUpperCase())
        if (!v.includes(camel)) {
          console.log(`       错位起点 #${k + 1}: 列 "${c}" 期望含 "${camel}"，实际为 "${v}"`)
          break
        }
      }
      if (cols.length > vals.length) {
        console.log(`       缺少值: ${cols.slice(vals.length).join(', ')}`)
      }
    }
  }
  if (!ok) failed++
}

if (failed > 0) {
  console.error(`\n有 ${failed} 条 insert 列数与值数不一致`)
  process.exit(1)
}
console.log('\n全部 insert 列数与值数一致')
