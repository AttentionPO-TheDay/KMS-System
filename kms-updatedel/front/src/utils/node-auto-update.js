import { getSelfAutoUpdate, claimSelfAutoUpdate, completeSelfAutoUpdate } from '@/api/pqkds/node-self'
import { generateAndRegisterNodeKey } from './node-initialization'
import { getToken } from './auth'
import { IS_DEMO } from './entry-mode'
import { getDemoContext } from './demo-context'
import { createAutoUpdateRunner } from './node-auto-update-runner.js'
import useUserStore from '@/store/modules/user'
import { resolvePrincipalType } from './principal'

export const AUTO_UPDATE_EVENT = 'kms-node-auto-update'
const runner = createAutoUpdateRunner({
  isLoggedIn: () => IS_DEMO ? getDemoContext()?.principalType === 'NODE' : Boolean(getToken()) && resolvePrincipalType(useUserStore()) === 'NODE',
  identity: () => IS_DEMO ? getDemoContext() : getToken(),
  getPolicies: getSelfAutoUpdate,
  claim: claimSelfAutoUpdate,
  complete: completeSelfAutoUpdate,
  rotate: generateAndRegisterNodeKey,
  changed: result => window.dispatchEvent(new CustomEvent(AUTO_UPDATE_EVENT, { detail: result }))
})

export function checkAutoUpdate() {
  return runner.tick()
}

export function startAutoUpdate() {
  const tick = () => checkAutoUpdate().catch(error => console.warn('自动更新检查失败：', error.message))
  const timer = setInterval(tick, 15000)
  window.addEventListener('focus', tick)
  window.addEventListener('online', tick)
  tick()
  return () => {
    clearInterval(timer)
    window.removeEventListener('focus', tick)
    window.removeEventListener('online', tick)
  }
}
