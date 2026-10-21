export function didConfirmed(record) {
  return record?.status === 'CONFIRMED' && record.transactionValid === true && record.metadataMatches === true
}

export function didStatusText(record) {
  if (!record) return '尚未关联 DID'
  if (didConfirmed(record)) return 'DID 上链已确认'
  if (record.status === 'CONFIRMED') return '确认凭证不完整'
  return ({
    PREPARING: '正在分配 SysPid', PREPARE_FAILED: 'SysPid 分配未完成',
    PREPARED: 'SysPid 已分配，待提交', PENDING_VERIFICATION: 'DID 待核验',
    FAILED: 'DID 核验未通过', DISABLED: 'DID 尚未启用'
  })[record.status] || 'DID 状态待核查'
}
