<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>密钥分发</h2>
        <p class="page-desc">
          选择接收节点、保护算法与<b>接收方密钥版本</b>。服务端按你指定的那一版公钥封装会话密钥，
          只有接收节点本地的对应私钥能解开 —— 有效期 1 到 168 小时，到期自动失效。
        </p>
      </div>
    </header>

    <el-row :gutter="16">
      <!-- ------------------------------------------------------------------
           发起分发（KMS-008 新请求契约）
           ------------------------------------------------------------------ -->
      <el-col :xs="24" :lg="14">
        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <span>发起分发</span>
              <el-tag v-if="nodes.length" size="small" type="info" effect="plain">
                可选节点 {{ nodes.length }} 个
              </el-tag>
            </div>
          </template>

          <!-- 身份：新契约是**节点到节点**，管理员账号没有节点身份，发不了 -->
          <el-alert
            v-if="!nodeLoading && !mapped"
            title="当前账号未关联任何节点"
            description="分发是节点之间的动作（发送方必须有自己的长期密钥）。请用节点账号登录后再分发。"
            type="warning"
            :closable="false"
            show-icon
            class="mb16"
          />

          <el-alert
            v-else-if="!nodesLoading && !nodes.length"
            title="你还没有被授权任何节点。请联系管理员在「节点鉴权」里为你授权后再分发。"
            type="warning"
            :closable="false"
            show-icon
            class="mb16"
          />

          <el-form label-width="130px" @submit.prevent>
            <el-form-item label="接收节点">
              <el-select
                v-model="form.receiverNodeCode"
                filterable
                placeholder="选择接收该会话密钥的节点"
                class="full-width"
                @change="handleReceiverChange"
              >
                <el-option
                  v-for="node in nodes"
                  :key="node.nodeCode"
                  :label="`${node.nodeName}（${node.nodeCode}）`"
                  :value="node.nodeCode"
                />
              </el-select>
            </el-form-item>

            <!--
              保护算法（计划 §3 的固定职责）：
                SM2 / SSCL / Kyber 保护 SM4；Falcon 只签名，**不是**保护算法。
              旧页面那套「抗量子 / 国密」二分已经去掉 —— 它把"用谁的密钥"
                和"用哪种算法"搅在一起；新契约里算法就是算法，一次选定。
            -->
            <el-form-item label="保护算法">
              <el-radio-group
                v-model="form.protectionAlgorithm"
                :disabled="!form.receiverNodeCode"
                @change="handleAlgorithmChange"
              >
                <el-radio-button label="KYBER">Kyber</el-radio-button>
                <el-radio-button label="SM2">SM2</el-radio-button>
                <el-radio-button label="SSCL">SSCL</el-radio-button>
              </el-radio-group>
              <div class="form-hint">Falcon 是签名算法，不提供机密性，不在保护算法之列。</div>
            </el-form-item>

            <el-form-item label="接收方密钥版本">
              <el-select
                v-model="form.recipientKeyRef"
                :loading="keysLoading"
                :disabled="!form.receiverNodeCode"
                placeholder="选择用接收方的哪一版公钥封装"
                class="full-width"
              >
                <el-option
                  v-for="key in usablePeerKeys"
                  :key="`${key.keyId}@${key.keyVersion}`"
                  :label="keyLabel(key)"
                  :value="`${key.keyId}@${key.keyVersion}`"
                />
              </el-select>
              <div class="form-hint">
                只列**可用于新工作**的版本（当前版本）。已被取代或已回收的版本不出现在这里 ——
                能不能用由服务端判（`allowsNewWork`），页面不另写一套。
              </div>
            </el-form-item>

            <el-form-item label="有效期（小时）">
              <el-input-number v-model="form.expiresInHours" :min="1" :max="168" />
              <div class="form-hint">1..168 小时，默认 24。到期后信封不再可用（不自动续期）。</div>
            </el-form-item>

            <el-form-item label="发送方 Falcon 版本">
              <el-tag v-if="falconReady" size="small" type="success" effect="plain">
                {{ falconKey?.keyId }} v{{ falconKey?.keyVersion }}
              </el-tag>
              <el-tag v-else size="small" type="danger" effect="plain">本机不可用</el-tag>
              <div class="form-hint">
                信封用**本机这把 Falcon 私钥**签名。两个条件都要满足：服务端说这一版可用
                （登记表），且**本机密钥库里有它的私钥** —— 换过设备或清过浏览器数据时，
                前者成立而后者不成立，提交会被服务端拒（`SIGNATURE_REQUIRED`）。
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="handleDistribute">
                分发
              </el-button>
              <el-button @click="loadNodes">刷新节点</el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="mapped && !nodeLoading && !falconReady"
            title="本机没有可用于签名的 Falcon 私钥"
            description="信封必须由发送节点本地签名。请在本机生成一把 Falcon 密钥（「密钥生成」页），或改用当初生成密钥的那台设备。"
            type="warning"
            :closable="false"
            show-icon
            class="mb16"
          />

          <el-alert v-if="result" type="success" :closable="false" show-icon class="mt8">
            <template #title>分发完成：批次 {{ result.batchId }}</template>
            <div class="result-body">
              <p>
                已按接收方 <strong>{{ result.recipientKeyId }} v{{ result.recipientKeyVersion }}</strong>
                （{{ result.protectionLabel }}）封好会话密钥，交给 {{ result.receiverNodeName }}。
              </p>
              <p>有效期至 {{ formatTime(result.expiresAt) }}；登记会话 {{ result.sessionCount }} 条。</p>
              <p v-if="result.signatureVerified">
                <b>服务端已验签通过</b>：信封用本机 Falcon 密钥
                <code>{{ result.falconKeyId }} v{{ result.falconKeyVersion }}</code> 签名，
                并由服务端按**同一版公钥**验证（载荷密钥哈希 <code>{{ result.localKeyHash }}</code>）。
              </p>
              <p v-else class="muted">
                ⚠️ 服务端未回执"已验签"，请把这条报给维护者（验过的请求才可能回这个字段）。
              </p>
              <p v-if="result.chainHash">链上存证：{{ result.chainHash }}</p>
              <!-- ⚠️ 存证没成功**如实说**，不与"分发成功"混成一句 ——
                   分发本身已经成立（信封落库、接收方能取），缺的是审计那一半。 -->
              <p v-else class="muted">链上存证未成功（分发本身已完成；审计缺口需要重试存证）。</p>
              <!-- KMS-012：本地会话密钥与"下一步在哪" -->
              <p v-if="result.sessionId && result.keyStored">
                会话 <code>{{ result.sessionId }}</code> 已建立（initiated）；本机已保存这把会话密钥的副本，
                你可以在「会话管理」里提交持有证明（确认），等对方处理完之后双方确认一致即建立。
              </p>
              <p v-else-if="result.sessionId" class="warn">
                ⚠️ 本机**没能**保存会话密钥副本（{{ result.keyStoreError }}）——
                分发本身已完成，但你这侧将无法提交确认。请把这条报给维护者。
              </p>
              <p v-else class="muted">本次没有建立节点到节点会话（没有对应的"待确认"）。</p>
            </div>
          </el-alert>

          <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="mt8">
            {{ errorMessage }}
          </el-alert>
        </el-card>
      </el-col>

      <!-- ------------------------------------------------------------------
           批次历史
           ------------------------------------------------------------------ -->
      <el-col :xs="24" :lg="10">
        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <span>我的分发批次</span>
              <el-button link type="primary" @click="loadBatches">刷新</el-button>
            </div>
          </template>

          <el-table :data="batches" size="small" v-loading="batchesLoading" empty-text="还没有分发记录">
            <el-table-column label="批次号" prop="batchId" min-width="170" show-overflow-tooltip />
            <el-table-column label="算法" prop="wrappingAlgorithm" width="86" />
            <el-table-column label="节点" width="64">
              <template #default="scope">{{ scope.row.nodeSuccessCount }}/{{ scope.row.nodeCount }}</template>
            </el-table-column>
            <el-table-column label="状态" width="88">
              <template #default="scope">
                <el-tag size="small" :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="scope">{{ formatTime(scope.row.createdAt) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>

<script setup>
/**
 * 密钥分发页 —— KMS-008 的**新请求契约**。
 *
 * 这一版删掉了旧"用户腿"的两样东西：
 *   1. 「我的解封密钥」（`sourceKeyId`）—— 那是"服务端为发起人本人也封一份"
 *      的旧模型。新模型是**节点到节点**：发送节点取接收节点的公钥封 SM4，
 *      没有"用户自己的那一份"；
 *   2. 「封装体系（抗量子/国密）」二分 —— 它把"用谁的密钥"与"用哪种算法"
 *      搅在一起。新契约里保护算法就是 SM2 / SSCL / Kyber 三选一。
 *
 * 新增的是**接收方密钥版本**：选定节点与算法后向服务端查它的长期密钥列表，
 * 选一版"当前版本"的。服务端按**这一版**核对 —— 旧实现读的是物化列
 * （"当前生产公钥"），请求里带了版本也传不进封装调用。
 *
 * KMS-009：**SM4 与封装搬到了本机**。本页现在自己做三件事：
 *   1. 生成 16 字节 SM4 载荷密钥；
 *   2. 用接收方**那一版**公钥封好（`provider.wrapForPeer`）；
 *   3. 用**本机 Falcon 私钥**签名（`signNodeEnvelope`）。
 * 服务端验签并登记（KMS-010），从此拿不到 SM4 明文（计划 §2.1）。
 *
 * 三条由服务端保证、前端只做体验优化：
 *   * 接收节点的密钥列表要对它有**授权**才拿得到（未授权 403）；
 *   * 保护算法白名单由服务端强制（Falcon 会被拒）；
 *   * 能不能用某一版由 `allowsNewWork` 回答（取自 `api_contract`，前端不另判）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'
import {
  createNodeDistribution,
  listDistributionBatches,
  listPeerKeys,
  listUserNodes
} from '@/services/user-distribution-api'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { buildKeyRef } from '@/utils/crypto/key-ref.js'
import { sealSessionSecret } from '@/utils/crypto/node-key-store.js'
import {
  buildNodeEnvelope,
  generatePayloadKey,
  newBatchId,
  signNodeEnvelope
} from '@/utils/crypto/envelope-signing.js'

/** 保护算法（规范名）。与 `api_contract.PROTECTION_ALGORITHMS` 一致，Falcon 不在其中。 */
const PROTECTION_ALGORITHMS = ['KYBER', 'SM2', 'SSCL']

const PROTECTION_LABELS = { KYBER: '抗量子 Kyber', SM2: '国密 SM2', SSCL: '国密 SSCL' }

const nodes = ref([])
const nodesLoading = ref(false)
const mapped = ref(false)
const nodeLoading = ref(true)
const selfNodeId = ref('')
/** 本机可用于签名的 Falcon 密钥（取自己方长期密钥里可用于新工作的那把）。 */
const falconKey = ref(null)
const falconReady = ref(false)
const peerKeys = ref([])
const keysLoading = ref(false)
const batches = ref([])
const batchesLoading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const result = ref(null)

const form = reactive({
  receiverNodeCode: '',
  protectionAlgorithm: 'KYBER',
  /** `${keyId}@${keyVersion}` —— 一个字符串比两个联动字段好判"选没选"。 */
  recipientKeyRef: '',
  expiresInHours: 24
})

/**
 * 可用于**新工作**的接收方密钥版本。
 *
 * ⚠️ 判据直接用服务端的 `allowsNewWork`，**不在前端另写一套状态判断** ——
 *    两份必然漂移，而漂移的表现是"界面显示可用、提交被告知不可用"（或更糟：
 *    界面隐藏了一个其实可用的版本）。这个字段与后端 `api_contract` 的状态集合绑定。
 */
const usablePeerKeys = computed(() => peerKeys.value.filter((key) => key.allowsNewWork === true))

const canSubmit = computed(() => Boolean(
  mapped.value && form.receiverNodeCode && form.recipientKeyRef
  && falconReady.value && !submitting.value
))

/**
 * 取本节点那把**可用于签名**的 Falcon 公钥记录，并确认**本机**有对应私钥。
 *
 * ⚠️ 两个条件是分开的，缺一不可：
 *    * 服务端说这把 Falcon 版本可用（`allowsNewWork` —— 登记表是事实来源）；
 *    * **本机密钥库里有它的私钥**（`hasKey`）。设备换了一台、或本地库被清过时，
 *      服务端照样说可用，而本机签不了名 —— 那种状态下提交会在服务端吃一个
 *      `SIGNATURE_REQUIRED`，看着像"服务端不认签名"，实际是本机缺材料。
 *      所以在页面上先判、并给出该做什么（去「密钥生成」页生成或换设备）。
 */
async function loadFalconKey() {
  falconKey.value = null
  falconReady.value = false
  if (!selfNodeId.value) {
    return
  }
  try {
    const data = await listSelfNodeKeys()
    const candidates = (data?.keys || []).filter(
      (k) => k.algorithm === 'FALCON' && k.allowsNewWork === true
    )
    for (const candidate of candidates) {
      const ref = buildKeyRef({
        nodeId: selfNodeId.value,
        algorithm: 'FALCON',
        keyId: candidate.keyId,
        version: candidate.keyVersion
      })
      if (await cryptoProvider.hasKey(ref)) {
        falconKey.value = { ...candidate, keyRef: ref }
        falconReady.value = true
        return
      }
    }
  } catch (error) {
    errorMessage.value = `加载本机签名密钥失败：${describeError(error)}`
  }
}

/** 把选中的 `keyId@version` 还原成两个字段（服务端要分开收）。 */
function parseKeyRef(ref) {
  const text = String(ref || '')
  const at = text.lastIndexOf('@')
  if (at <= 0) {
    return null
  }
  const keyVersion = Number(text.slice(at + 1))
  if (!Number.isInteger(keyVersion) || keyVersion < 1) {
    return null
  }
  return { keyId: text.slice(0, at), keyVersion }
}

function keyLabel(key) {
  return `${key.keyId} v${key.keyVersion}（${key.statusLabel || key.status}）`
}

async function loadSelf() {
  nodeLoading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    selfNodeId.value = data?.node?.nodeId || ''
    await loadFalconKey()
  } catch (error) {
    errorMessage.value = `加载节点身份失败：${describeError(error)}`
  } finally {
    nodeLoading.value = false
  }
}

async function loadNodes() {
  nodesLoading.value = true
  try {
    const data = await listUserNodes()
    nodes.value = data?.nodes || []
    // 授权可能被管理员收回：把已不在列表里的选择清掉，
    // 否则提交时只会拿到一个"越权"错误，而用户看不出是自己选了个失效节点。
    const allowed = new Set(nodes.value.map((n) => n.nodeCode))
    if (form.receiverNodeCode && !allowed.has(form.receiverNodeCode)) {
      form.receiverNodeCode = ''
      peerKeys.value = []
      form.recipientKeyRef = ''
    }
  } catch (error) {
    errorMessage.value = `加载节点失败：${describeError(error)}`
  } finally {
    nodesLoading.value = false
  }
}

/**
 * 拉接收方在当前算法下的密钥列表。
 *
 * ⚠️ 路径里用的是**业务编号**（`nodeCode`），不是 `/user-nodes/` 回的 `nodeId`
 *    （那是主键）。传错的表现是"节点明明在，接口说它不存在"。
 */
async function loadPeerKeys() {
  peerKeys.value = []
  form.recipientKeyRef = ''
  if (!form.receiverNodeCode) {
    return
  }
  keysLoading.value = true
  try {
    const data = await listPeerKeys(form.receiverNodeCode, [form.protectionAlgorithm])
    peerKeys.value = data?.keys || []
    // 只有一版可用时直接选中：一次点击就能提交，少一步无意义的交互。
    // ⚠️ 多于一个候选时**不预选** —— 预选一个"看起来对"的版本，
    //    用户按下去就发出去了，而他并没有真正做选择。
    if (usablePeerKeys.value.length === 1) {
      const only = usablePeerKeys.value[0]
      form.recipientKeyRef = `${only.keyId}@${only.keyVersion}`
    }
  } catch (error) {
    errorMessage.value = `加载接收方密钥列表失败：${describeError(error)}`
  } finally {
    keysLoading.value = false
  }
}

function handleReceiverChange() {
  errorMessage.value = ''
  result.value = null
  return loadPeerKeys()
}

function handleAlgorithmChange() {
  errorMessage.value = ''
  result.value = null
  return loadPeerKeys()
}

async function loadBatches() {
  batchesLoading.value = true
  try {
    const data = await listDistributionBatches({ limit: 50 })
    batches.value = data?.items || []
  } catch (error) {
    errorMessage.value = `加载批次失败：${describeError(error)}`
  } finally {
    batchesLoading.value = false
  }
}

async function handleDistribute() {
  const parsed = parseKeyRef(form.recipientKeyRef)
  if (!canSubmit.value || parsed === null) {
    return
  }
  // 选中的那一版接收方公钥 —— 它的 `publicKey` 是**比对形式的小写 hex**
  // （服务端 `_public_key_hex` 统一换算过），正是 `wrapForPeer` 要的入参形状。
  const peerKey = usablePeerKeys.value.find(
    (k) => k.keyId === parsed.keyId && Number(k.keyVersion) === parsed.keyVersion
  )
  if (!peerKey) {
    errorMessage.value = '选中的接收方密钥版本已不在列表里，请重新选择。'
    return
  }

  submitting.value = true
  errorMessage.value = ''
  result.value = null
  try {
    // ---- 以下三步全在**本机**完成（KMS-009）----
    // 1) 本地生成 SM4 载荷密钥；
    const payloadKey = generatePayloadKey()
    // 2) 本地用接收方那一版公钥封装；
    // 3) 本地用 Falcon 私钥签名。
    // `batchId` / `expiresAt` 也在这里定 —— 签名要覆盖它们（见
    // `envelope-signing.js` 文件头的说明），服务端仍会校验形状与上界。
    const batchId = newBatchId()
    const expiresAt = new Date(Date.now() + Number(form.expiresInHours) * 3600 * 1000).toISOString()
    const { envelope, keyHash, wrapping } = await buildNodeEnvelope({
      provider: cryptoProvider,
      payloadKey,
      wrapping: form.protectionAlgorithm,
      recipientPublicKeyHex: peerKey.publicKey,
      batchId,
      senderNodeId: selfNodeId.value,
      receiverNodeId: form.receiverNodeCode,
      recipientKeyId: parsed.keyId,
      recipientKeyVersion: parsed.keyVersion,
      expiresAt
    })
    const signature = await signNodeEnvelope(cryptoProvider, falconKey.value.keyRef, envelope)

    const data = await createNodeDistribution({
      receiverNodeId: form.receiverNodeCode,
      protectionAlgorithm: form.protectionAlgorithm,
      recipientKeyId: parsed.keyId,
      recipientKeyVersion: parsed.keyVersion,
      // KMS-010：把**本机签名用的那一版** Falcon 一并交上去 —— 服务端按它
      // 查公钥验签（计划 §6.1）。两者必须同源：都是上面那把 `falconKey`，
      // 页面不另选一把、服务端也不替它挑"当前生产版本"。
      falconKeyId: falconKey.value.keyId,
      falconKeyVersion: falconKey.value.keyVersion,
      batchId,
      expiresAt,
      envelope,
      signature,
      keyHash,
      wrappingAlgorithm: wrapping
    })
    result.value = {
      batchId: data?.batchId,
      recipientKeyId: data?.recipientKeyId,
      recipientKeyVersion: data?.recipientKeyVersion,
      protectionLabel: PROTECTION_LABELS[data?.protectionAlgorithm] || data?.protectionAlgorithm || '',
      receiverNodeName: data?.receiverNodeName || form.receiverNodeCode,
      sessionCount: data?.sessionCount ?? 0,
      expiresAt: data?.expiresAt,
      chainHash: data?.chainHash || '',
      // KMS-010：服务端**验过签**才回这个字段（验不过的请求在服务端就被拒、走不到这里）。
      signatureVerified: Boolean(data?.signatureVerified),
      falconKeyId: data?.falconKeyId || falconKey.value.keyId,
      falconKeyVersion: data?.falconKeyVersion ?? falconKey.value.keyVersion,
      localKeyHash: keyHash,
      // KMS-012：这条分发对应的会话 + 本机那把 K 的落库结果。
      sessionId: data?.sessionId || '',
      sessionStatus: data?.sessionStatus || '',
      keyStored: false,
      keyStoreError: ''
    }
    // KMS-012（计划 §7 阶段 4：「解封得到 SM4 后保存到本地会话密钥库」）：
    // 发起方这把 K 是它自己生成的，同样要**留在本机** —— 会话双方各自提交
    // `HMAC(K, session_id)`，发起方不存 K 就永远确认不了（刷新一次即失联，
    // 而页面上看不出为什么）。存失败**如实显示**，不吞掉：
    // 那不是"分发失败"（信封已经发出去、服务端已登记），而是"本机少了一条
    // 后续要用的材料"，用户需要知道。
    if (result.value.sessionId) {
      try {
        await sealSessionSecret(result.value.sessionId, payloadKey)
        result.value.keyStored = true
      } catch (error) {
        result.value.keyStoreError = String(error?.message || error)
      }
    }
    ElMessage.success('分发完成')
    await loadBatches()
  } catch (error) {
    // 服务端的拒绝理由已经足够具体（没授权 / 版本不对 / 已回收 / 算法不允许），
    // 按**错误码**给下一步，而不是把文案原样抛回去 —— 用户要知道的是"该做什么"。
    errorMessage.value = describeError(error)
    // 版本类的失败多半是因为列表已经过时（对方刚更新/回收），顺手刷一次，
    // 让用户下一眼看到的是当前真实可用的版本。
    if (error?.errorCode && error.errorCode !== 'NOT_AUTHORIZED') {
      await loadPeerKeys()
    }
  } finally {
    submitting.value = false
  }
}

/**
 * 把错误翻成"下一步做什么"。
 *
 * ⚠️ 分支**按 `error.errorCode`**（由 `@/api/pqkds/http` 拦截器从
 *    `body.data.error_code` 附上），不匹配 `error.message` —— 文案随时会改，
 *    而匹配文案的失败方式是**静默走错分支**，不会有任何一处报错。
 */
function describeError(error) {
  const fallback = error?.message || String(error) || '未知错误'
  switch (error?.errorCode) {
    case 'NOT_AUTHORIZED':
      return '当前账号没有向该节点分发的权限（或未关联节点）。请联系管理员在「节点鉴权」里授权。'
    case 'KEY_NOT_FOUND':
      return '接收方的这一版密钥不存在 —— 它可能刚被更新或回收。列表已刷新，请重选一版。'
    case 'KEY_REVOKED':
      return '这一版已被回收（终态），不会再恢复。请改用列表里的其它版本。'
    case 'KEY_VERSION_MISMATCH':
      return '这一版不是接收方当前的生产版本（已被取代）。请选标记为「当前版本」的那一版。'
    case 'KEY_EXPIRED':
      return '这一版已过期，请改选其它版本或让对方续期。'
    case 'ALGORITHM_NOT_ALLOWED':
      return '该算法不能用于保护会话密钥（Falcon 只做签名）。请选 SM2 / SSCL / Kyber。'
    case 'SIGNATURE_REQUIRED':
      return '服务端没有收到签名。本机这把 Falcon 私钥可能不在密钥库里（换过设备或清过数据）—— 请在本机重新生成一把 Falcon 密钥后再分发。'
    case 'SIGNATURE_INVALID':
      return '服务端验签没通过（信封内容与本机签名对不上）。最可能的两种原因：本机这把 Falcon 私钥与登记的那一版不是一对（重新生成过），或信封在本机之外被改动过。请刷新后重试；若仍失败，把这一步报给维护者。'
    case 'ENVELOPE_TAMPERED':
      return '信封的摘要与服务端重算的对不上（两侧的规范化序列化口径可能漂移了）。这是实现问题，请把它报给维护者，不要重试。'
    case 'INVALID_PARAMETER':
      return `参数不合法：${fallback}`
    default:
      return fallback
  }
}

function statusText(status) {
  return { success: '全部成功', partial: '部分成功', pending: '进行中', failed: '失败' }[status] || status || '-'
}

function statusType(status) {
  return { success: 'success', partial: 'warning', pending: 'info', failed: 'danger' }[status] || 'info'
}

function formatTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  await Promise.all([loadSelf(), loadNodes(), loadBatches()])
})
</script>

<style scoped>
.page-head h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

.page-desc {
  margin: 0 0 16px;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.panel {
  border-radius: 10px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.full-width {
  width: 100%;
}

.form-hint {
  margin-top: 4px;
  color: var(--kms-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.result-body p {
  margin: 4px 0;
  font-size: 13px;
}

.muted {
  color: var(--kms-text-secondary);
}

.warn {
  color: var(--kms-warning-strong, #ff7d00);
}

.mb16 {
  margin-bottom: 16px;
}

.mt8 {
  margin-top: 8px;
}
</style>