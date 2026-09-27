// 一次性清理：逐页删除"说明性文字"（按文本内容精确定位，避免误伤功能性提示）。
//
// 政策
// ----
// 删：页面副标题、模块原理说明、重复解释、纯介绍性横幅
// 留：① 运行时报错与结果回显  ② 有实际后果的警告（审批后需回退、私钥/密钥文件会丢、
//     新建节点需等待）  ③ 空状态下的操作指引（无授权节点、未导入密钥文件）
//
// 用法：node tools/_strip-page-text.mjs [--dry]
import { readFileSync, writeFileSync } from 'node:fs'

const dry = process.argv.includes('--dry')

// 每条：文件、要删的文本片段（可跨行，用正则）、说明
const RULES = [
  // ---------------- 管理端 ----------------
  ['kms-updatedel/front/src/views/chain/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '区块链存证页顶部说明横幅'],
  ['kms-updatedel/front/src/views/commonParam/index.vue',
    /[ \t]*<el-alert\s+:title="`当前展示[\s\S]*?\/>\s*\n?/, '公共参数页动态说明横幅'],
  ['kms-updatedel/front/src/views/distOverview/index.vue',
    /[ \t]*<span class="sub">分发模块的节点[^<]*<\/span>\s*\n?/, '分发总览页副标题'],
  ['kms-updatedel/front/src/views/distOverview/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '分发总览页说明横幅'],
  ['kms-updatedel/front/src/views/distlogs/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '分发日志页说明横幅'],
  ['kms-updatedel/front/src/views/keyautoupdate/user.vue',
    /[ \t]*<el-alert\s+title="密钥自动更新管理"[\s\S]*?(?:\/>|<\/el-alert>)\s*\n?/, '密钥自动更新页标题横幅'],
  ['kms-updatedel/front/src/views/keypool/index.vue',
    /[ \t]*<span class="sub">预分配密钥[^<]*<\/span>\s*\n?/, '密钥池页副标题'],
  ['kms-updatedel/front/src/views/keypool/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '密钥池页说明横幅'],
  ['kms-updatedel/front/src/views/nodeauth/index.vue',
    /[ \t]*<el-alert\s+type="info"[\s\S]*?<\/el-alert>\s*\n?/, '节点鉴权页说明横幅'],
  ['kms-updatedel/front/src/views/nodes/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '节点管理页说明横幅'],
  ['kms-updatedel/front/src/views/nodes/index.vue',
    /[ \t]*<div class="form-hint">节点ID \/ 名称 \/ 地址在服务端是只读的[\s\S]*?<\/div>\s*\n?/, '节点编辑弹窗只读说明'],
  ['kms-updatedel/front/src/views/query/keyList/index.vue',
    /[ \t]*<el-alert v-if="pageMode === 'mine'"[\s\S]*?\/>\s*\n?/, '密钥查询页模式说明（mine）'],
  ['kms-updatedel/front/src/views/query/keyList/index.vue',
    /[ \t]*<el-alert v-else-if="pageMode === 'chain'"[\s\S]*?\/>\s*\n?/, '密钥查询页模式说明（chain）'],
  ['kms-updatedel/front/src/views/query/keyList/index.vue',
    /[ \t]*<el-alert\s+title="该记录已纳入公共查询总表[\s\S]*?\/>\s*\n?/, '密钥查询页存证说明横幅'],
  ['kms-updatedel/front/src/views/sessions/index.vue',
    /[ \t]*<span class="sub">节点之间协商出来的会话密钥[^<]*<\/span>\s*\n?/, '会话密钥页副标题'],
  ['kms-updatedel/front/src/views/sessions/index.vue',
    /[ \t]*<el-alert type="info"[\s\S]*?<\/el-alert>\s*\n?/, '会话密钥页说明横幅'],

  // ---------------- 用户端 ----------------
  ['kms-user/front/src/views/distribute/DistributeView.vue',
    /[ \t]*<p class="muted">请到「对称密钥查看」导入密钥文件后解开这些信封。<\/p>\s*\n?/, '分发结果旁的使用说明'],
  ['kms-user/front/src/views/generate/GenerateView.vue',
    /[ \t]*<p class="muted">SM2\/SSCL 在浏览器侧生成本地份额[^<]*<\/p>\s*\n?/, '生成页顶部说明'],
  ['kms-user/front/src/views/generate/GenerateView.vue',
    /[ \t]*<p class="muted">SM2\/SSCL 的本地部分私钥只保留在当前页面[^<]*<\/p>\s*\n?/, '本地材料面板说明'],
  ['kms-user/front/src/views/generate/GenerateView.vue',
    /[ \t]*<p class="muted">默认聚焦当前登录用户的生成记录[^<]*<\/p>\s*\n?/, '生成记录页说明'],
  ['kms-user/front/src/views/generate/GenerateView.vue',
    /[ \t]*<p class="muted">用于核对 SSCL 公共参数[^<]*<\/p>\s*\n?/, '公共参数核对说明'],
  ['kms-user/front/src/views/lifecycle/LifecycleView.vue',
    /[ \t]*<span class="muted">开启密钥托管自动更新需要该权限[^<]*<\/span>\s*\n?/, '自动更新权限说明']
]

let changed = 0
for (const [file, pattern, label] of RULES) {
  const src = readFileSync(file, 'utf8')
  const m = src.match(pattern)
  if (!m) {
    console.log(`  [跳过] ${label} —— 未匹配到（可能已删）  ${file}`)
    continue
  }
  const next = src.replace(pattern, '')
  if (!dry) writeFileSync(file, next, 'utf8')
  changed++
  console.log(`  [删除] ${label}  (${m[0].replace(/\s+/g, ' ').trim().slice(0, 60)}…)`)
}
console.log(`\n共处理 ${changed} 处${dry ? '（dry-run）' : ''}`)
