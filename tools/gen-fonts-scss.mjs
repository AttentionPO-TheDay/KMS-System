// 生成 design-tokens/fonts.scss：自托管字体声明
// 用法：node tools/gen-fonts-scss.mjs
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dt = resolve(root, 'design-tokens')

const header = `/* ============================================================================
 * KMS 自托管字体（design-tokens 单一真源）
 * ----------------------------------------------------------------------------
 * 本文件由 tools/gen-fonts-scss.mjs 生成，请勿手工编辑。
 *
 * 为什么自托管：原先只有系统字体栈，中文在 Windows 上落到「微软雅黑」，
 * 小字号下笔画偏细、字面偏宽、缺少中间字重，观感不佳且跨平台不一致。
 *
 * 采用：
 *   - Inter Variable（拉丁）：字面紧凑、字重轴 100-900，适合数据密集型后台
 *   - Noto Sans SC Variable（中文）：思源黑体 Google 版，字重轴完整
 *
 * 中文被切成 101 个 unicode-range 分片，浏览器只按需下载用到的分片，
 * 首屏不会加载全部体积。
 *
 * 字体文件位于同目录 fonts/，由 Vite 打包时按相对路径解析并输出到 dist。
 * ========================================================================== */

/* ---------- Inter Variable（拉丁） ---------- */
@font-face {
  font-family: 'Inter Variable';
  font-style: normal;
  font-display: swap;
  font-weight: 100 900;
  src: url('./fonts/inter-latin-wght-normal.woff2') format('woff2-variations');
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
    U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215,
    U+FEFF, U+FFFD;
}

@font-face {
  font-family: 'Inter Variable';
  font-style: normal;
  font-display: swap;
  font-weight: 100 900;
  src: url('./fonts/inter-latin-ext-wght-normal.woff2') format('woff2-variations');
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304,
    U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0,
    U+2113, U+2C60-2C7F, U+A720-A7FF;
}

/* ---------- Noto Sans SC Variable（中文，按 unicode-range 分片） ---------- */
`

const notoPath = resolve(dt, 'node_modules/@fontsource-variable/noto-sans-sc/index.css')
let noto = readFileSync(notoPath, 'utf8')
noto = noto.replace(/\.\/files\//g, './fonts/')

const out = header + '\n' + noto
writeFileSync(resolve(dt, 'fonts.scss'), out, 'utf8')

const faces = (out.match(/@font-face/g) || []).length
const urls = (out.match(/url\(/g) || []).length
console.log(`已生成 design-tokens/fonts.scss`)
console.log(`  @font-face: ${faces}  url(): ${urls}`)
console.log(`  残留 ./files/ 引用: ${(out.match(/\.\/files\//g) || []).length}`)