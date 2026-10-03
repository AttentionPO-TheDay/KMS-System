<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>当前节点</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §10.1 节点工作台的"身份"部分：这个账号在 KMS 里对应哪个节点、
        处于什么状态、被允许做什么。

        ⚠️ 本页**只读**。节点资料（名称/类型/所属域/权限等级）由管理员在
        「节点管理」里设定，节点自己不能改 —— 能自改权限等级的节点等于没有权限模型。
      -->

      <!-- 管理员账号没有对应节点。这不是错误，是"这个账号不是节点"，如实说明 -->
      <el-alert
        v-if="!loading && !mapped"
        title="当前账号没有对应的 KMS 节点"
        type="info"
        :closable="false"
        show-icon
        description="管理员账号不映射到节点。节点资料由管理员在「节点管理」中创建并分配。"
      />

      <template v-else-if="mapped">
        <el-descriptions :column="2" border class="mb16">
          <el-descriptions-item label="节点名称">
            {{ node.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="节点 ID">
            <span class="mono">{{ node.nodeId || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="节点类型">
            {{ node.nodeType || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="所属域">
            {{ node.domainId || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="权限等级">
            <el-tag size="small" :type="levelTagType(node.permissionLevel)" effect="plain">
              {{ node.permissionLevel || '-' }}
            </el-tag>
            <span class="hint">{{ node.levelLabel }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="初始化状态">
            <el-tag size="small" :type="statusTagType(node.status)">
              {{ node.status || '-' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="初始化时间">
            {{ formatTime(node.initializedAt) }}
          </el-descriptions-item>
          <el-descriptions-item label="绑定设备">
            <!-- §4.4 设备绑定：密钥绑在哪台设备上。与「本地密钥环境」页的本机
                 deviceId 比对，才能发现"我用的不是当初那台设备"。 -->
            <span class="mono">{{ node.keyDeviceId || '（未绑定）' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">权限能力</div>
        <!--
          capabilities 由后端按 permission_level 下发（见 node_self_views.py 的注释：
          "前端据此隐藏/禁用入口，而不是自己维护一份等级表 —— 两份表必然漂移，
          而漂移的表现是'界面能点、后端拒绝'"）。这里原样展示，不自行推导。
        -->
        <div class="cap-list">
          <el-tag
            v-for="cap in allCapabilities"
            :key="cap.key"
            size="small"
            :type="cap.granted ? 'success' : 'info'"
            :effect="cap.granted ? 'light' : 'plain'"
          >
            {{ cap.label }}{{ cap.granted ? '' : '（未授权）' }}
          </el-tag>
        </div>

        <div class="section-title">基础密钥就绪情况</div>
        <!-- 这里只看"服务端登记了没有"；本机私钥是否在场由「本地密钥环境」页判断。
             两者会不一致（比如换设备后服务端有公钥、本机没私钥），
             那正是 §6 要提示"当前设备尚未绑定该节点"的场景。 -->
        <el-row :gutter="12">
          <el-col :span="6" v-for="k in keyCards" :key="k.key">
            <div class="key-card" :class="{ ok: k.ready }">
              <div class="key-name">{{ k.label }}</div>
              <div class="key-state">{{ k.ready ? '已登记' : '缺失' }}</div>
            </div>
          </el-col>
        </el-row>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.2 节点信息 → 当前节点。
 *
 * 数据来自 `GET /pqkds-api/node-self/`（node_self_views.py）。
 * 身份**不由参数传递** —— 后端从令牌自省取 userId 再经 Node.sys_user_id 映射，
 * 所以这里没有任何 nodeId 参数，传了也不作数（刻意如此，避免让人以为
 * 可以替别的节点查看）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode } from '@/api/pqkds/node-self'

const loading = ref(false)
const mapped = ref(false)
const node = ref({})

/** §8.4 的四个能力。与 doc/admin-node-login-design.md §9.3 的 L1/L2/L3 对应。 */
const CAPABILITY_LABELS = {
  query: '查询',
  generate: '密钥生成',
  distribute: '密钥分发',
  // ⚠️ 键必须是后端 `node_permission.CAP_ROTATE` 的值 `rotate`。
  // 写成 `update` 的表现是：L3 节点这边**永远**显示"更新：未授权"
  // （granted 里有 rotate，但没有 update 这个键），而界面上看不出任何异常。
  rotate: '更新',
  revoke: '回收'
}

const allCapabilities = computed(() => {
  const granted = new Set(node.value.capabilities || [])
  const keys = Object.keys(CAPABILITY_LABELS)
  // 以后端下发的为准；后端没提到的能力一律显示"未授权"（最小权限）
  return keys.map((key) => ({ key, label: CAPABILITY_LABELS[key], granted: granted.has(key) }))
})

const KEY_LABELS = { kyber: 'Kyber', falcon: 'Falcon', sm2: 'SM2', sscl: 'SSCL' }

const keyCards = computed(() =>
  Object.entries(KEY_LABELS).map(([key, label]) => ({
    key,
    label,
    ready: Boolean(node.value.keys?.[key])
  }))
)

function statusTagType(status) {
  if (status === 'ACTIVE') return 'success'
  if (status === 'DISABLED') return 'danger'
  return 'warning'
}

function levelTagType(level) {
  // L1 只读最弱、L3 最高：用颜色区分"这个节点能做的事有多少"
  if (level === 'L3') return 'success'
  if (level === 'L2') return 'warning'
  return 'info'
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const res = await getSelfNode()
    mapped.value = Boolean(res?.mapped)
    node.value = res?.node || {}
  } catch (error) {
    ElMessage.error(error?.message || '获取节点信息失败')
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
.cap-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.key-card {
  border: 1px solid var(--kms-border);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  background: var(--kms-surface-2, #fafafa);
}
.key-card.ok {
  border-color: var(--kms-success-strong, #00b42a);
  background: var(--kms-success-subtle, #e8ffea);
}
.key-name {
  font-size: 13px;
  color: var(--kms-text-secondary);
  margin-bottom: 6px;
}
.key-state {
  font-size: 15px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
</style>
