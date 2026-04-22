import { ref, computed } from 'vue'
import { API } from '../api'

export const health = ref(null)
export const scenarios = ref([])
export const runs = ref([])
export const securityRuns = ref([])
export const proofRuns = ref([])

export const error = ref('')

export const passCount = computed(() => runs.value.filter((item) => item.status === 'passed').length)

export async function loadHealth() {
  const payload = await API.getHealth()
  health.value = payload
}

export async function loadScenarios() {
  const payload = await API.getScenarios()
  scenarios.value = payload.data || []
}

export async function loadRuns() {
  const payload = await API.getRuns()
  runs.value = payload.data || []
}

export async function loadSecurityRuns() {
  const payload = await API.getSecurityRuns()
  securityRuns.value = payload.data || []
}

export async function loadProofRuns() {
  const payload = await API.getProofRuns()
  proofRuns.value = payload.data || []
}

export async function loadAll() {
  const results = await Promise.allSettled([
    loadHealth(),
    loadScenarios(),
    loadRuns(),
    loadSecurityRuns(),
    loadProofRuns()
  ])

  const failed = results.find((item) => item.status === 'rejected')
  error.value = failed?.reason?.message || ''
}

export { API }
