// Registration success is not a chain receipt. Never label an unverified transaction as confirmed.
export function chainEvidenceText(binding) {
  if (!binding) return '未配置存证'
  if (binding.status === 'CONFIRMED') return binding.transactionValid === true && binding.metadataMatches === true ? '已上链' : '回执未验证'
  return ({ PENDING: '等待上链', PREPARED: '交易已准备', SUBMITTED: '已提交，待确认',
    PENDING_VERIFICATION: '回执确认中', NOT_CONFIGURED: '连接不可用，待重试',
    NOT_REGISTERED: '尚未入队', FAILED: '上链失败', PAUSED: '上链已暂停', STALE_BINDING: '历史版本存证' })[binding.status] || '尚未确认'
}
