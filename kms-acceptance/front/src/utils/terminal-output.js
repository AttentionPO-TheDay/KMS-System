const valid = value => value !== undefined && value !== null && value !== ''
const number = value => value.toLocaleString('zh-CN', { maximumFractionDigits: 3 })
export function logTime(value) {
  if (!value) return '--:--:--.---'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '--:--:--.---' : `${date.toLocaleTimeString('zh-CN', { hour12: false })}.${String(date.getMilliseconds()).padStart(3, '0')}`
}

export function terminalLines(events, spans = []) {
  const lines = []
  for (const e of events || []) {
    const time = logTime(e.at)
    lines.push({ id: `${e.id}-action`, time, tag: e.kind || 'CALL', state: 'info', text: e.kind ? e.action : `${e.from} -> ${e.to} | ${e.action}` })
    for (const [index, [key, value]] of (e.fields || []).entries()) {
      if (valid(value)) lines.push({ id: `${e.id}-field-${index}`, time: '', tag: 'DATA', state: 'data', text: `${key}=${value}` })
    }
    const elapsed = Number.isFinite(e.durationMs) && e.durationMs >= 0 ? ` | elapsed=${number(e.durationMs)} ms` : ''
    lines.push({ id: `${e.id}-result`, time: '', tag: e.kind && e.state === 'info' ? 'DATA' : e.state === 'success' ? 'OK' : e.state === 'failed' ? 'FAIL' : 'INFO', state: e.state || 'info', text: `${e.output}${elapsed}` })
  }
  for (const [index, span] of (spans || []).entries()) {
    if (!span.worker || !Number.isFinite(span.startMs) || !Number.isFinite(span.endMs) || span.startMs < 0 || span.endMs < span.startMs) continue
    lines.push({ id: `worker-${index}`, time: '', tag: span.kind === 'process' ? 'PROCESS' : 'THREAD', state: 'data', text: `${span.worker} | start=${number(span.startMs)} ms end=${number(span.endMs)} ms elapsed=${number(span.endMs - span.startMs)} ms` })
  }
  return lines
}

export function terminalText(lines) {
  return lines.map(line => `${line.time ? `[${line.time}] ` : ''}[${line.tag}] ${line.text}`).join('\n')
}
