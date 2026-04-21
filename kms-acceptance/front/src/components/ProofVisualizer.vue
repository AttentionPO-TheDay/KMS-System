<template>
  <div class="proof-wrapper glass-panel">
    <div class="panel-header">
      <div>
        <h2>全链路混合证明测试靶场</h2>
        <p class="subtitle">针对生命周期系统进行小批量 <code>BATCH_UPDATE</code> 脉冲，抓取区块链存证并验证默克尔树 (Merkle Root) 与半诚实承诺 (Semi-honest Proof)。</p>
      </div>
      <span class="badge" :class="latestProofRun?.passed ? 'ok' : 'warn'">
        {{ latestProofRun?.passed ? 'ZK VERIFIED' : 'PENDING' }}
      </span>
    </div>

    <div class="proof-config tech-bar">
      <label class="field horizontal">
        <span>BATCH SIZE</span>
        <input v-model="proofForm.batchSize" type="number" min="1" max="32" class="tech-input small-input"/>
      </label>
      <label class="field horizontal">
        <span>MERKLE FANOUT</span>
        <input v-model="proofForm.treeFanout" type="number" min="2" max="128" class="tech-input small-input"/>
      </label>
      <label class="field horizontal">
        <span>PROOF MODE</span>
        <input v-model="proofForm.proofMode" class="tech-input small-input"/>
      </label>
      <label class="field horizontal" style="flex: 1">
        <span>LIFECYCLE HOOK</span>
        <input v-model="proofForm.lifecycleBaseUrl" placeholder="默认内部通信 URL" class="tech-input"/>
      </label>
      <button class="btn-primary cyber-btn" :disabled="proofLoading" @click="runProofVisualTest">
        <span class="cyber-btn-text">{{ proofLoading ? '证明中...' : 'INJECT PROOF' }}</span>
      </button>
      <button class="btn-ghost" @click="loadProofRuns">↻</button>
      <p v-if="error" class="error-msg">⚠️ {{ error }}</p>
    </div>

    <div v-if="latestProofRun" class="proof-grid">
      <!-- Tree Check -->
      <article class="proof-card inner-glass">
        <div class="proof-card-head">
          <h3>Merkle Tree Hash Consistency</h3>
          <span class="badge" :class="proofStatusClass(latestProofRun.treeCheck)">{{ proofStatusLabel(latestProofRun.treeCheck) }}</span>
        </div>
        <p class="desc">{{ latestProofRun.treeCheck?.message }}</p>
        
        <div class="tree-root-box">
          <span class="tag">MAIN ROOT</span>
          <code class="hash">{{ shortHash(latestProofRun.summary?.batchRoot) }}</code>
        </div>

        <div class="tree-parents">
          <div v-for="group in proofParentGroups" :key="group.parent" class="tree-parent">
            <div class="parent-node">
              <span>Branch</span>
              <code class="hash">{{ shortHash(group.parent) }}</code>
            </div>
            <div class="leaf-row">
              <div v-for="leaf in group.leaves" :key="leaf.recordId" class="leaf-node">
                <div class="leaf-id">#{{ leaf.nodeIndex }} / {{ leaf.keyId }}</div>
                <div class="leaf-path">{{ leaf.treePath }}</div>
              </div>
            </div>
          </div>
        </div>
      </article>

      <!-- Proof Check -->
      <article class="proof-card inner-glass">
        <div class="proof-card-head">
          <h3>Zero-Knowledge Commitment</h3>
          <span class="badge" :class="proofStatusClass(latestProofRun.proofCheck)">{{ proofStatusLabel(latestProofRun.proofCheck) }}</span>
        </div>
        <p class="desc">{{ latestProofRun.proofCheck?.message }}</p>
        
        <div class="proof-flow">
          <div class="flow-item">
            <span>Commitment Presence</span>
            <strong :class="latestProofRun.summary?.allCommitmentsPresent?'text-ok':'text-error'">
              {{ latestProofRun.summary?.allCommitmentsPresent ? '100% SECURE' : 'LEAK DETECTED' }}
            </strong>
          </div>
          <div class="flow-item">
            <span>Consistency Hash</span>
            <strong :class="latestProofRun.summary?.allConsistencyHashesPresent?'text-ok':'text-error'">
              {{ latestProofRun.summary?.allConsistencyHashesPresent ? '100% MATCH' : 'MISMATCH' }}
            </strong>
          </div>
          <div class="flow-item" style="grid-column: span 2">
            <span>Global Verification Engine</span>
            <strong class="text-info">{{ latestProofRun.summary?.verifyMessage || 'AWAITING' }}</strong>
          </div>
        </div>

        <div class="proof-records-list">
          <div v-for="record in (latestProofRun.records || [])" :key="record.recordId" class="record-row">
            <div class="record-id">K_{{ record.keyId }} [v{{ record.keyVersion }}]</div>
            <div class="record-hashes">
              <span class="hash-tag">CMT <span class="hash">{{ shortHash(record.commitment) }}</span></span>
              <span class="hash-tag">CSY <span class="hash">{{ shortHash(record.consistencyHash) }}</span></span>
            </div>
          </div>
        </div>
      </article>
    </div>
    
    <div v-else class="empty-state">
      <div class="empty-icon">⚛️</div>
      <p>证明网络空闲中。配置 Batch Size 后发起 Inject 指令。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { proofRuns, API, loadProofRuns } from '../store'

const proofLoading = ref(false)
const error = ref('')

const proofForm = ref({
  batchSize: 5, treeFanout: 4, proofMode: 'semi_honest', lifecycleBaseUrl: ''
})

const latestProofRun = computed(() => proofRuns.value[0] || null)

const proofParentGroups = computed(() => {
  const run = latestProofRun.value
  if (!run || !run.records) return []
  const groups = new Map()
  for (const record of run.records) {
    const key = record.parentBatchId || 'ROOT_FALLBACK'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(record)
  }
  return Array.from(groups.entries()).map(([parent, leaves]) => ({
    parent, leaves: leaves.sort((a, b) => Number(a.nodeIndex || 0) - Number(b.nodeIndex || 0))
  }))
})

function proofStatusClass(check) {
  if (!check) return 'warn'
  return check.passed ? 'ok' : 'error'
}
function proofStatusLabel(check) {
  if (!check) return 'N/A'
  return check.passed ? 'VERIFIED' : 'FAILED'
}
function shortHash(value) {
  if (!value) return '-'
  if (value.length <= 18) return value
  return `${value.slice(0, 10)}...${value.slice(-6)}`
}

async function runProofVisualTest() {
  error.value = ''
  proofLoading.value = true
  try {
    await API.postProofRun({
      batchSize: Number(proofForm.value.batchSize),
      treeFanout: Number(proofForm.value.treeFanout),
      proofMode: proofForm.value.proofMode,
      lifecycleBaseUrl: proofForm.value.lifecycleBaseUrl
    })
    await loadProofRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    proofLoading.value = false
  }
}
</script>

<style scoped>
.proof-wrapper { grid-column: 1 / -1; margin-bottom: 24px; }
.subtitle { color: #8b9eb3; margin-top: 8px; font-size: 14px; }

.tech-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(0, 0, 0, 0.4);
  padding: 16px;
  border-radius: 12px;
  margin-top: 20px;
  margin-bottom: 24px;
}
.horizontal {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-direction: row;
  margin: 0;
}
.small-input { width: 80px; }
.error-msg { color: #ff4d4f; font-size: 13px; margin: 0; }

.proof-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.inner-glass {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 24px;
}
.proof-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.proof-card-head h3 { margin: 0; font-size: 16px; color: #e2e8f0; }
.desc { color: #64748b; font-size: 13px; margin-bottom: 20px; }

.hash {
  font-family: 'JetBrains Mono', monospace;
  color: #00f2fe;
}
.tree-root-box {
  background: rgba(0, 242, 254, 0.1);
  border: 1px dashed rgba(0, 242, 254, 0.3);
  padding: 12px;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
.tree-parent {
  margin-bottom: 12px;
}
.parent-node {
  background: rgba(255,255,255,0.05);
  padding: 8px 12px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  border-radius: 6px 6px 0 0;
}
.leaf-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
  padding: 12px;
  background: rgba(0,0,0,0.2);
  border-radius: 0 0 6px 6px;
}
.leaf-node {
  background: rgba(255,255,255,0.05);
  padding: 8px;
  border-radius: 4px;
  text-align: center;
}
.leaf-id { font-size: 11px; color: #fff; margin-bottom: 4px; }
.leaf-path { font-size: 10px; color: #64748b; font-family: monospace; }

.proof-flow {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}
.flow-item {
  background: rgba(0,0,0,0.3);
  padding: 12px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}
.flow-item span { font-size: 11px; color: #8b9eb3; margin-bottom: 4px; }
.flow-item strong { font-size: 15px; }

.record-row {
  display: flex;
  justify-content: space-between;
  padding: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  align-items: center;
}
.record-id { font-size: 13px; color: #e2e8f0; font-family: monospace; }
.record-hashes { display: flex; gap: 12px; }
.hash-tag { font-size: 11px; color: #64748b; }
.text-info { color: #00f2fe; }

@media (max-width: 1024px) {
  .proof-grid { grid-template-columns: 1fr; }
  .tech-bar { flex-wrap: wrap; }
}
</style>
