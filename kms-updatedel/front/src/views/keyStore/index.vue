<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>本地密钥环境</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §10.2：只显示**存在 / 缺失 / 异常**，不展示私钥内容。
        这条不是"界面省事"，是设计边界：u、Kyber/Falcon 私钥、设备认证私钥
        都不能离开本机（文档 §12），后端根本没有它们，页面自然也拿不到。
      -->

      <el-alert
        v-if="mismatch"
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
        title="当前设备尚未绑定该节点"
        description="服务端登记了这个节点，但本机找不到它的私钥材料。请联系管理员重新激活；本版本不做跨设备私钥同步（文档 §6）。"
      />

      <el-alert
        v-if="!loading && !nodeId"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
        title="当前账号没有对应的 KMS 节点"
        description="管理员账号不映射到节点，因此没有本地密钥库。"
      />

      <template v-if="nodeId">
        <div class="section-title">本机密钥库（NodeKeyStore）</div>
        <el-descriptions :column="2" border class="mb16">
          <el-descriptions-item label="安全存储">
            <el-tag size="small" :type="storeTagType" effect="plain">{{ storeLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备认证凭据">
            <!-- §3.1：本机私钥是否在场。这是**密码学**判据（不可导出、只能签），
                 取代了改造前那个可被任意脚本改写的 deviceId 字符串比对。 -->
            <el-tag size="small" :type="hasCredential ? 'success' : 'danger'" effect="plain">
              {{ hasCredential ? '在场' : '缺失' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="本机公钥指纹">
            <span class="mono">{{ fingerprint || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="服务端登记指纹">
            <!-- 两者一致 = 本机就是当初激活的那台设备 -->
            <span class="mono">{{ node.keyDeviceId || '（未绑定）' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备匹配">
            <el-tag size="small" :type="deviceMatches ? 'success' : 'danger'">
              {{ deviceMatches ? '一致' : '不一致' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">四套基础密钥</div>
        <!--
          每套密钥有两个独立事实，必须分列，不能合成一个"状态"：
            服务端登记 —— 公钥是否已上报（后端能查到）
            本机私钥   —— 私钥是否在本机密钥库里
          两者不一致是可处置的状态（换设备、初始化中途失败），
          合成一列会把它显示成普通的"缺失"，掩盖真正的原因。
        -->
        <el-table :data="keyRows" border>
          <el-table-column label="算法" width="140" prop="label" />
          <el-table-column label="服务端公钥" width="140" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.registered ? 'success' : 'danger'" effect="plain">
                {{ row.registered ? '已登记' : '缺失' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="本机私钥" width="140" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.local ? 'success' : 'danger'" effect="plain">
                {{ row.local ? '在场' : '缺失' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="260" prop="note" />
        </el-table>

        <div class="section-title">设备认证密钥</div>
        <p class="note">
          设备认证密钥由节点首次激活时在本机生成，私钥只保存在本地，仅用于节点登录认证，
          不参与 SM4 分发、Kyber 封装、Falcon 签名或 SM2 / SSCL 无证书生成（文档 §3.1）。
          它不可导出，因此这里只能报告"是否在场"，无法显示其内容。
        </p>

        <div class="section-title">登录绑定文件</div>
        <!--
          本机（IndexedDB）的登录记账：每次节点登录成功后写下/刷新一份。
          它回答"这台浏览器现在的绑定是哪个节点、绑在哪台设备上、上次什么时候登录的"。

          ⚠️ 绑定文件里**没有任何秘密**（设备私钥在 deviceKeys store，指纹是公开量），
             所以这里可以整份展示；它也不是登录的**依据** —— 登录靠设备私钥签名。
        -->
        <p class="note">
          每次节点登录成功后，本机写下/刷新一份绑定文件（节点、设备公钥指纹、首次与最近登录时间）。
          本机只保留最近登录的那一个节点：登录别的节点时会先确认、再清除旧的绑定与登录身份。
        </p>
        <el-alert
          v-if="bindingMismatch"
          class="mb16"
          type="warning"
          :closable="false"
          show-icon
          :title="`本机的绑定属于另一个节点：${machineBinding.nodeId}`"
          :description="`当前节点是 ${nodeId}，但本机最近一次登录的是 ${machineBinding.nodeId}。切回 ${nodeId} 登录会清除那一份绑定。`"
        />
        <el-descriptions v-if="binding" :column="2" border class="mb16">
          <el-descriptions-item label="绑定节点">
            <span class="mono">{{ binding.nodeId }}</span>
            <span v-if="binding.nodeName" class="hint">（{{ binding.nodeName }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="设备公钥指纹">
            <span class="mono">{{ binding.deviceFingerprint || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="首次登录">
            {{ formatTime(binding.createdAt) }}
          </el-descriptions-item>
          <el-descriptions-item label="最近登录">
            {{ formatTime(binding.lastLoginAt) }}
            <span v-if="binding.loginCount" class="hint">第 {{ binding.loginCount }} 次</span>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-else-if="!loading && nodeId"
          class="mb16"
          type="info"
          :closable="false"
          show-icon
          title="本机还没有该节点的绑定文件"
          description="不影响登录与密钥使用 —— 登录一次即会写上。多见于绑定功能上线之前激活的节点。"
        />
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.2 节点信息 → 本地密钥环境。
 *
 * 两个数据源合并：
 *   1. `GET /pqkds-api/node-self/`  —— 服务端登记了哪些公钥、密钥绑在哪台设备
 *   2. 本机 IndexedDB 的 NodeKeyStore —— 私钥是否真的在本机
 *
 * ⚠️ 只有**第 2 项**能回答"本机有没有私钥"。服务端没有私钥，也无从知道
 *    本机状态 —— 这正是无证书体系的设计边界，不是接口的缺陷。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode } from '@/api/pqkds/node-self'
import { deviceFingerprint, hasDeviceKey } from '@/utils/crypto/device-credential'
import { inspectNodeKeys } from '@/utils/crypto/node-key-store'
import { currentBinding, readBinding } from '@/utils/crypto/node-binding'

const loading = ref(false)
const node = ref({})
const nodeId = ref('')
/** 本机是否持有该节点的设备认证私钥（§3.1） */
const hasCredential = ref(false)
/** 本机设备公钥指纹；与 `node.keyDeviceId` 应当一致 */
const fingerprint = ref('')
/** 本机密钥库里出现了哪些算法（小写：sm2/sscl/kyber/falcon） */
const localAlgorithms = ref([])
/** 本机（IndexedDB）的登录绑定文件；没有则为 null（见 node-binding.js） */
const binding = ref(null)
/**
 * 本机**最近一次登录**绑定的那个节点（可能不是当前节点）。
 *
 * ⚠️ 变量名不能叫 `currentBinding` —— 那会遮蔽从 node-binding.js 引入的
 *    同名函数，`load()` 里的调用会静默变成"读这个 ref 的值"（它此刻是 null），
 *    于是本机绑定永远显示不出来，且不报任何错。
 */
const machineBinding = ref(null)

const bindingMismatch = computed(
  () => Boolean(machineBinding.value?.nodeId) && machineBinding.value.nodeId !== nodeId.value
)

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}
/** 本机密钥库是否因为浏览器不支持而不可用 */
const storeUnavailable = ref(false)

const KEY_DEFS = [
  { key: 'sm2', label: 'SM2', note: '无证书：秘密 u 与完整私钥能力只在本机（§7.1）' },
  { key: 'sscl', label: 'SSCL', note: '无证书：秘密 u 与完整私钥能力只在本机（§7.1）' },
  { key: 'kyber', label: 'Kyber', note: '浏览器 KeyGen，公钥上传、私钥留本地（§7.2）' },
  { key: 'falcon', label: 'Falcon', note: '负责业务签名，不承担 SM4 加密（§7.3）' }
]

const keyRows = computed(() =>
  KEY_DEFS.map((def) => ({
    ...def,
    registered: Boolean(node.value.keys?.[def.key]),
    local: localAlgorithms.value.includes(def.key)
  }))
)

/** 服务端登记了节点，但本机一把私钥都没有 → 换设备了（§6） */
const mismatch = computed(
  () => Boolean(nodeId.value) && !loading.value && localAlgorithms.value.length === 0
)

const deviceMatches = computed(() => {
  const bound = String(node.value.keyDeviceId || '').trim()
  if (!bound) return false
  // 比的是**设备公钥指纹**（公开量、由不可导出的私钥推出），
  // 不是改造前那个可被任意脚本改写的浏览器级 deviceId 字符串。
  return bound === String(fingerprint.value || '').trim()
})

const storeTagType = computed(() => (storeUnavailable.value ? 'danger' : 'success'))
const storeLabel = computed(() => (storeUnavailable.value ? '不可用' : 'IndexedDB'))

async function load() {
  loading.value = true
  try {
    const res = await getSelfNode()
    node.value = res?.node || {}
    nodeId.value = node.value.nodeId || ''

    if (nodeId.value) {
      hasCredential.value = await hasDeviceKey(nodeId.value)
      fingerprint.value = await deviceFingerprint(nodeId.value)
      // inspectNodeKeys 的判据是"任意一套基础密钥在不在本机"，
      // 而不是"四套都在"：初始化做到一半（比如生成完 SM2 就断网了）
      // 与"新设备什么都没有"是两回事，处置也不同（前者续做，后者要重新初始化）。
      const found = await inspectNodeKeys(nodeId.value)
      localAlgorithms.value = (found?.algorithms || []).map((a) => String(a).toLowerCase())
      // 绑定文件：该节点这一份（显示细节）与本机当前那一份（判是否换了节点）。
      // 两者各查一次而不是从同一个列表里挑 —— 前者按节点精确取，
      // 后者按"最近登录"取，口径不同，混成一个列表会少一种情形。
      binding.value = await readBinding(nodeId.value)
      machineBinding.value = await currentBinding()
    } else {
      localAlgorithms.value = []
      binding.value = null
      machineBinding.value = null
    }
  } catch (error) {
    // 浏览器不支持 WebCrypto / IndexedDB 时，读本地密钥库会失败。
    // 这时要如实说"本机密钥库不可用"，而不是显示成"私钥缺失"——
    // 后者会把人引向"重新初始化"，而真正的问题是环境不支持。
    if (!nodeId.value) {
      ElMessage.error(error?.message || '获取节点信息失败')
    }
    storeUnavailable.value = true
    localAlgorithms.value = []
    // 密钥库都读不到时，绑定文件同样读不到 —— 如实清空，而不是留着上一次的旧值
    binding.value = null
    machineBinding.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mb16 { margin-bottom: 16px; }
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.hint {
  margin-left: 8px;
  color: var(--kms-text-secondary);
  font-size: 12px;
}
.section-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.note {
  margin: 0;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
</style>
