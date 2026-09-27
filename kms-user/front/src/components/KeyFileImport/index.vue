<template>
  <div class="key-file-import">
    <el-button size="small" :icon="Upload" @click="dialogOpen = true">
      导入密钥文件
    </el-button>
    <el-tag v-if="keyring.size > 0" size="small" type="success" effect="plain">
      本机已存 {{ keyring.size }} 把
    </el-tag>

    <el-dialog v-model="dialogOpen" title="导入密钥文件" width="640px" append-to-body destroy-on-close>
      <el-alert
        title="密钥文件是本机解开分发信封的唯一凭据。文件只在本机解析，不会上传到服务端。"
        type="info"
        :closable="false"
        show-icon
        class="mb12"
      />

      <!-- 选择文件 / 粘贴内容 两条路都留着：前者是常规路径，
           后者在用户只存了文本（比如从聊天记录里翻出来）时很有用 -->
      <el-tabs v-model="mode">
        <el-tab-pane label="选择文件" name="file">
          <input
            ref="fileInputRef"
            type="file"
            accept=".json,application/json"
            class="file-input"
            @change="handleFilePicked"
          />
        </el-tab-pane>
        <el-tab-pane label="粘贴内容" name="paste">
          <el-input
            v-model="pasted"
            type="textarea"
            :rows="6"
            placeholder="把密钥文件的 JSON 内容粘贴到这里"
          />
          <el-button class="mt8" type="primary" :loading="importing" @click="handlePasteImport">
            导入
          </el-button>
        </el-tab-pane>
      </el-tabs>

      <p v-if="errorMessage" class="error-text mt12">{{ errorMessage }}</p>
      <p v-if="successMessage" class="success-text mt12">{{ successMessage }}</p>

      <template #footer>
        <el-button @click="dialogOpen = false">关 闭</el-button>
      </template>
    </el-dialog>

    <!-- 已导入清单：让用户能确认"哪把密钥我现在能解开" -->
    <el-dialog v-model="listOpen" title="本机密钥环" width="640px" append-to-body>
      <el-table :data="keyring.summaries" size="small">
        <el-table-column label="密钥ID" prop="keyId" width="90" />
        <el-table-column label="算法" prop="algorithm" width="90" />
        <el-table-column label="导出时间" prop="createdAt" min-width="180" />
        <el-table-column label="操作" width="90">
          <template #default="scope">
            <el-button link type="danger" @click="keyring.remove(scope.row.keyId)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="listOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 密钥文件导入组件（计划 §7 P3 步骤 0b）
 *
 * 职责边界要说清楚：
 *   * 本组件只做"把用户自己保存的 `d_a` 导入本机密钥环"这一件事；
 *   * 它**不会**把文件内容发给服务端（这是 R1' 红线）；
 *   * 校验交给 `utils/key-file.js` —— 校验不通过一律报错，绝不"尽力而为"地用错密钥。
 */
import { ref } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import useKeyringStore from '@/store/modules/keyring'
import { parseKeyFile } from '@/utils/key-file'

const emit = defineEmits(['imported'])

const keyring = useKeyringStore()
const dialogOpen = ref(false)
const listOpen = ref(false)
const mode = ref('file')
const fileInputRef = ref(null)
const pasted = ref('')
const importing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

async function doImport(text) {
  errorMessage.value = ''
  successMessage.value = ''
  importing.value = true
  try {
    // 先解析校验（拿到摘要用于回显），再交给密钥环落库。
    // 两步分开是为了让错误信息能区分"文件本身有问题"与"与本机已有记录冲突"。
    const parsed = await parseKeyFile(text)
    await keyring.importKeyFile(parsed)
    successMessage.value = `已导入：密钥 ${parsed.key_id}（${parsed.algorithm || '未知算法'}）`
    pasted.value = ''
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
    emit('imported', parsed)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    importing.value = false
  }
}

async function handleFilePicked(event) {
  const file = event.target.files?.[0]
  if (!file) {
    return
  }
  try {
    await doImport(await file.text())
  } catch (error) {
    errorMessage.value = `读取文件失败：${error.message}`
  }
}

async function handlePasteImport() {
  if (!pasted.value.trim()) {
    errorMessage.value = '请先粘贴密钥文件内容'
    return
  }
  await doImport(pasted.value)
}

defineExpose({ open: () => (dialogOpen.value = true), openList: () => (listOpen.value = true) })
</script>

<style scoped>
.key-file-import {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.file-input {
  display: block;
  width: 100%;
  padding: 8px 0;
  color: var(--kms-text-secondary);
}

.mt8 {
  margin-top: 8px;
}

.mt12 {
  margin-top: 12px;
}

.error-text {
  color: var(--kms-danger-strong);
  font-size: var(--kms-font-size-sm, 13px);
  margin: 0;
}

.success-text {
  color: var(--kms-success-strong);
  font-size: var(--kms-font-size-sm, 13px);
  margin: 0;
}
</style>