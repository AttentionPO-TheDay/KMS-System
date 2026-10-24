const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hourCycle: 'h23',
  hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3
})

export function formatTime(value) {
  if (!value) return ''
  const timestamp = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}+08:00` : value
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? String(value) : timeFormatter.format(date)
}
