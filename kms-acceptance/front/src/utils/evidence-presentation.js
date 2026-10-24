// Classify by recorded purpose, never by request position: attacks can use the
// same session endpoints as setup. Keep unknown and unsuccessful steps visible.
export function securityRequestGroups(run) {
  const groups = { core: [], preparation: [], controls: [], cleanup: [] }
  for (const trace of run?.requests || []) {
    const name = trace.name || '', url = trace.url || ''
    const transportFailed = trace.outcome === 'error' || !trace.statusCode || trace.statusCode >= 500
    let group = 'core'
    if (!transportFailed && !name.includes('发送非法请求')) {
      if (/\/context\/logout(?:\?|$)/.test(url)) group = 'cleanup'
      else if (/攻击[前后]|复查合法/.test(name) && trace.statusCode >= 200 && trace.statusCode < 300 && !/businessCode=(?!200(?:\s|$))/.test(trace.message || '')) group = 'controls'
      else if (/建立独立测试会话|进入测试节点/.test(name) && trace.statusCode >= 200 && trace.statusCode < 300 && !/businessCode=(?!200(?:\s|$))/.test(trace.message || '')) group = 'preparation'
    }
    groups[group].push(trace)
  }
  return groups
}

export function parseCostFields(rawCost) {
  const fields = {}
  for (const line of String(rawCost || '').split('\n')) {
    const colon = line.indexOf(':')
    if (colon > 0) fields[line.slice(0, colon).trim()] = line.slice(colon + 1).trim()
  }
  return fields
}

const performanceMethods = {
  'generate-tps': {
    title: '生成接口吞吐测量',
    steps: ['按本次配置并发请求密钥生成接口。', '统计完成的 HTTP 请求，扣除非成功响应。', '以成功响应数除以配置测量时长。'],
    scope: '按本轮接口成功响应统计结果展示。'
  },
  'update-tps': {
    title: '固定密钥版本更新',
    steps: ['选取已有的 6000 把 SM2 密钥，保存更新前版本。', '每把提交一次更新请求。', '核验版本递增且材料改变，以完成数计算更新速率。'],
    scope: '从首次提交计时至数据库落库核验，包含排队和状态查询；不含密钥池准备、前置快照及异步上链等待。'
  },
  'revoke-tps': {
    title: '异常检测与自动回收',
    steps: ['注入 6000 条异常密钥和正常对照。', '执行异常扫描、回收及关联池项和会话失效。', '按实际回收的独立密钥数及扫描回收耗时计算速率。'],
    scope: '计时包含异常扫描、数据库回收及关联失效；不含样本准备、清理及链上确认。'
  },
  'revoke-rate': {
    title: '最终回收成功比例',
    steps: ['注入异常样本并记录实际发起回收的密钥。', '执行各批次回收并核查最终状态。', '以最终回收成功数除以实际发起数，统计失败和未发起数量。'],
    scope: '已发起但失败的密钥计入分母，未发起的单列；最终回收率与每秒回收速率独立计算。'
  },
  'symmetric-reclaim-tps': {
    title: '到期 SM4 保护包回收',
    steps: ['准备到期 SM4 保护包及未到期和保留状态对照。', '筛选并删除到期池项，提交数据库事务。', '核查实际删除数量与对照，以回收阶段耗时计算速率。'],
    scope: '计时包含数据库筛选、删除和提交；不含样本准备、回收后核验、清理、HTTP 通信及节点本地文件销毁。'
  }
}

export const performanceMethod = run => run?.generationEvidence ? { title: '独立SSCL生成及登记核验', scope: '独立输入的生成登记及材料核验记录。计时包含数据库登记及状态核验。' } : performanceMethods[run?.scenarioId] || null

export function performanceCalculation(run, scenario) {
  const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: 3 }) : '—'
  let count, elapsed, formula
  if (run?.generationEvidence) {
    count = run.generationEvidence.verified ? run.generationEvidence.completed : null; elapsed = run.generationEvidence.elapsedMs
    formula = '核验有效且去重后的独立密钥数 ÷ 生成请求至登记核验耗时（秒）'
  } else if (run?.symmetricEvidence) {
    count = run.symmetricEvidence.reclaimed; elapsed = run.symmetricEvidence.elapsedMs
    formula = '实际回收到期 SM4 数 ÷ 回收耗时（秒）'
  } else if (run?.abnormalEvidence) {
    const e = run.abnormalEvidence
    if (run.scenarioId === 'revoke-rate') return { formula: '最终回收成功数 ÷ 实际发起回收数 × 100%', substitution: `${number(e.revoked)} ÷ ${number(e.attempted)} × 100%`, value: Number.isFinite(e.revoked) && Number.isFinite(e.attempted) && e.attempted > 0 ? e.revoked * 100 / e.attempted : null }
    count = e.revoked; elapsed = e.elapsedMs
    formula = '实际回收的独立异常密钥数 ÷ 扫描回收耗时（秒）'
  } else if (run?.fixedUpdateEvidence) {
    count = run.fixedUpdateEvidence.verified ? run.fixedUpdateEvidence.completed : null
    elapsed = run.fixedUpdateEvidence.elapsedMs
    formula = '核验完成更新的独立密钥数 ÷ 提交至落库核验耗时（秒）'
  } else if (run?.scenarioId === 'generate-tps') {
    const s = run.summary
    const valid = Number.isFinite(s?.totalRequests) && Number.isFinite(s?.non2xxResponses)
    count = valid ? Math.max(0, s.totalRequests - s.non2xxResponses) : null
    const durationIndex = run.wrkCommand?.indexOf('-d') ?? -1
    const recordedDuration = (durationIndex >= 0 ? /^(\d+(?:\.\d+)?)([smh])$/.exec(run.wrkCommand[durationIndex + 1] || '') : null)
      || /^Running (\d+(?:\.\d+)?)([smh]) test\b/m.exec(s?.rawOutput || '')
    const seconds = recordedDuration ? Number(recordedDuration[1]) * ({ s: 1, m: 60, h: 3600 }[recordedDuration[2]]) : (run.config?.durationSeconds ?? scenario?.durationSeconds)
    return { formula: 'HTTP 成功响应数 ÷ 配置测量时长（秒）', substitution: `(${number(s?.totalRequests)} − ${number(s?.non2xxResponses)}) ÷ ${number(seconds)}`, value: count !== null && Number.isFinite(seconds) && seconds > 0 ? count / seconds : null }
  } else return null
  return { formula, substitution: `${number(count)} ÷ (${number(elapsed)} / 1000)`, value: count !== null && Number.isFinite(count) && Number.isFinite(elapsed) && elapsed > 0 ? count * 1000 / elapsed : null }
}
