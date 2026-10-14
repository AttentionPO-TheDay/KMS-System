/**
 * 节点工作台准入与首次初始化完整性是两个不同概念。
 *
 * 已激活节点可以主动回收某一算法的当前密钥；在补充新版本之前，该算法
 * 暂时不能承接新业务，但节点仍应进入工作台处理其它密钥和后续恢复操作。
 * 真正需要拦截的是：服务端仍有可用版本，而当前浏览器缺少或持有不匹配的
 * 私钥材料。该风险由 inspection 行的 complete/lifecycleUnavailable 区分。
 */
export function canEnterNodeWorkspace(inspection = {}) {
  const algorithms = Array.isArray(inspection.algorithms) ? inspection.algorithms : []
  return Boolean(
    inspection.mapped &&
    inspection.node?.status === 'ACTIVE' &&
    algorithms.length > 0 &&
    algorithms.every(row => row.complete || row.lifecycleUnavailable)
  )
}

/** 已激活节点某算法有历史登记，但当前没有可承接新业务的版本。 */
export function classifyUnavailableAlgorithm(rows, nodeStatus) {
  const history = Array.isArray(rows) ? rows : []
  if (nodeStatus !== 'ACTIVE' || history.length === 0 || history.some(row => row.allowsNewWork)) {
    return null
  }
  const latest = history[0]
  return {
    latestServer: latest,
    state: latest.status === 'REVOKED' ? 'REVOKED' : 'NO_ACTIVE_KEY'
  }
}
