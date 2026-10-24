import test from 'node:test'
import assert from 'node:assert/strict'
import { formatTime } from './date-time.js'

test('performance timestamps show hours, minutes, seconds and milliseconds', () => {
  assert.equal(formatTime('2026-10-23T14:55:40+08:00'), '14:55:40.000')
  assert.equal(formatTime('2026-10-23T14:55:40.422169'), '14:55:40.422')
  assert.equal(formatTime('2026-10-23T14:55:40.422169+08:00'), '14:55:40.422')
  assert.equal(formatTime('2026-10-23T06:55:40.354Z'), '14:55:40.354')
  assert.equal(formatTime('2026-10-23T00:00:00+08:00'), '00:00:00.000')
})

test('absent and invalid timestamps keep existing fallback behavior', () => {
  assert.equal(formatTime(undefined), '')
  assert.equal(formatTime(null), '')
  assert.equal(formatTime(''), '')
  assert.equal(formatTime('未记录'), '未记录')
})
