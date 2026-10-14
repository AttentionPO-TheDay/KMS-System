// Scoped mechanical copy removal. Interactive/error/safety states are excluded.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { parse } from '@vue/compiler-sfc'
import { baseParse } from '@vue/compiler-dom'

const targets = ['preallocate', 'distribute', 'keyupdate', 'generate', 'domains', 'nodeauth',
  'selfAuth', 'selfNode', 'keyStore', 'keyautoupdate', 'workbench', 'crossDomain',
  'adminSummary', 'securityMonitor', 'distOverview', 'algorithm', 'keydelete', 'generateHistory']
const classes = new Set(['page-desc', 'subtitle', 'hint', 'domain-note', 'security-note',
  'key-update__lead', 'gen-create__section-note', 'form-hint', 'kh-note', 'note',
  'key-revoke__toolbar-note', 'gen-history__pk-note'])
const write = process.argv.includes('--write')
for (const directory of targets) {
  const root = join('src/views', directory)
  for (const file of readdirSync(root).filter(file => file.endsWith('.vue'))) {
    const path = join(root, file), source = readFileSync(path, 'utf8')
    const { descriptor } = parse(source)
    if (!descriptor.template) continue
    const removals = [], offset = descriptor.template.loc.start.offset
    function visit(node) {
      if (node.type === 1) {
        const className = node.props.find(prop => prop.type === 6 && prop.name === 'class')?.value?.content || ''
        // No conditional hints or interactive content. Do not remove live messages.
        if (className.split(/\s+/).some(name => classes.has(name))
          && !node.props.some(prop => prop.type === 7)
          && !node.loc.source.includes('{{')
          && !/<(?:el-|button|input|a\b|router-link)/.test(node.loc.source)) {
          removals.push([offset + node.loc.start.offset, offset + node.loc.end.offset])
          return
        }
      }
      for (const child of node.children || []) visit(child)
    }
    visit(baseParse(descriptor.template.content))
    let output = source
    for (const [start, end] of removals.sort((a,b) => b[0]-a[0])) output = output.slice(0,start)+output.slice(end)
    output = output.replace(/^[\t ]+(?=\r?$)/gm, '')
    if (output === source) continue
    if (write) writeFileSync(path, output)
    console.log(`${write ? 'TRIM' : 'PREVIEW'} ${path}: ${removals.length} explanatory blocks`)
  }
}
