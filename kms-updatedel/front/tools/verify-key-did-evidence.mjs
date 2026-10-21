import assert from 'node:assert/strict'
import test from 'node:test'
import { didConfirmed, didStatusText } from '../src/utils/key-did-evidence.js'

test('only a complete real receipt counts as confirmed', () => {
  const confirmed = { status: 'CONFIRMED', transactionValid: true, metadataMatches: true }
  assert.equal(didConfirmed(confirmed), true)
  for (const record of [null, {}, { status: 'CONFIRMED' }, { ...confirmed, metadataMatches: null },
    { ...confirmed, transactionValid: false }, { ...confirmed, status: 'PENDING_VERIFICATION' }]) {
    assert.equal(didConfirmed(record), false)
    assert.notEqual(didStatusText(record), 'DID 上链已确认')
  }
  assert.equal(didStatusText({ status: 'PREPARE_FAILED' }), 'SysPid 分配未完成')
})
