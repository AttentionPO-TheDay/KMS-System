// 全站"说明性文字"清单：逐页列出候选文案节点，供人工逐条决定去留。
// 判据：class 含 muted/sub/hint/note/tip/desc/help/explain/pq-mode 等描述性语义，
//       或 <el-alert> 横幅；文本长度 > 20 字。
// 用法：node tools/_text-inventory.mjs [admin|user]
import { readFileSync } from 'node:fs'
import { globSync } from 'node:fs'

const which = process.argv[2] || 'all'
const roots = []
if (which === 'all' || which === 'admin') roots.push('kms-updatedel/front/src/views')
if (which === 'all' || which === 'user') roots.push('kms-user/front/src/views')

const CLASS_RE = /class="[^"]*(?:muted|form-hint|\bsub\b|hint|note|tip|desc|help|explain|pq-mode|intro|lead|summary)[^"]*"/i
const files = roots.flatMap((r) => globSync(`${r}/**/*.vue`))

let total = 0
for (const file of files.sort()) {
  const lines = readFileSync(file, 'utf8').split(/\r?\n/)
  const items = []

  lines.forEach((line, idx) => {
    // el-alert 横幅（记录起始行，整体算一条）
    if (/<el-alert\b/.test(line)) {
      items.push({ line: idx + 1, kind: 'el-alert', text: line.replace(/\s+/g, ' ').trim().slice(0, 90) })
      return
    }
    if (!CLASS_RE.test(line)) return
    const text = line.replace(/<[^>]+>/g, ' ').replace(/\{\{[^}]*\}\}/g, '{{…}}').replace(/\s+/g, ' ').trim()
    if (text.length > 20) {
      items.push({ line: idx + 1, kind: 'desc-text', text: text.slice(0, 110) })
    }
  })

  if (!items.length) continue
  total += items.length
  console.log(`\n${file.replace(/\\/g, '/')}   (${items.length} 条)`)
  for (const it of items) console.log(`  L${String(it.line).padStart(4)}  [${it.kind}]  ${it.text}`)
}
console.log(`\n合计 ${total} 条，覆盖 ${files.length} 个页面文件`)
