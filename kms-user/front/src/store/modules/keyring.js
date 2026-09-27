import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { KEY_FILE_KIND, parseKeyFile, serializeKeyFile } from '@/utils/key-file'

/**
 * 本机密钥环：保存用户导入的密钥文件（`d_a`）。
 *
 * 计划 §7 P3 步骤 0b
 * =============================================================================
 * 用户要解开分发过来的信封，就必须持有对应密钥的 `d_a`。服务端只有 KGC 分片，
 * 浏览器端的本地份额 `u` 又从不持久化 —— 所以 `d_a` 只能由用户自己保管。
 *
 * 存放位置：**localStorage**，按 `key_id` 索引。
 *
 * ⚠️ 安全边界（写在这里，避免后人误解）
 * ------------------------------------
 * 1. localStorage 里的 `d_a` 是**明文**。它能被同源的任何脚本读到，
 *    因此本机制防的是"密钥丢失"，**不是** XSS。后续增强是用用户口令派生密钥
 *    加密存储（见计划里那条"后续增强"）。
 * 2. 绝不把这些内容发给服务端 —— 由 `tools/verify-p1.mjs` 的 R1' 断言守着。
 * 3. 这是**用户自己的**密钥环，不是服务端同步的资产。换浏览器就要重新导入文件。
 */

const STORAGE_KEY = 'kms-user-keyring-v1'

function readRaw() {
  try {
    const text = window.localStorage.getItem(STORAGE_KEY)
    if (!text) {
      return {}
    }
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    // 存储被写坏时不要把整个应用带崩：当作空密钥环，用户重新导入即可
    return {}
  }
}

function writeRaw(map) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
}

const useKeyringStore = defineStore('keyring', () => {
  /** { [key_id]: keyFile } */
  const entries = ref(readRaw())

  /** 已导入的密钥数量 */
  const size = computed(() => Object.keys(entries.value).length)

  /** 该密钥是否已经有可用的 d_a */
  function has(privateKeyId) {
    return Boolean(entries.value[String(privateKeyId)])
  }

  function get(privateKeyId) {
    return entries.value[String(privateKeyId)] || null
  }

  /**
   * 导入一份密钥文件（文本或已解析对象）。
   *
   * 校验失败会抛错 —— 调用方必须把错误显示出来，不允许静默忽略：
   * 用错的密钥去解密只会得到"解不开"，而用户不会知道是自己导错了文件。
   */
  async function importKeyFile(source) {
    const keyFile = typeof source === 'string' ? await parseKeyFile(source) : await parseKeyFile(source)
    const id = String(keyFile.key_id)

    const existing = entries.value[id]
    if (existing && existing.private_share !== keyFile.private_share) {
      // 同一 key_id 但私钥不同 —— 说明其中一份是错的，必须让人来判断，
      // 悄悄覆盖会让"为什么解不开"变成一个查不出来的问题。
      throw new Error(
        `密钥 ${id} 已存在且私钥份额不同。请先确认哪一份是正确的再导入（当前不会自动覆盖）。`
      )
    }

    entries.value = { ...entries.value, [id]: keyFile }
    writeRaw(entries.value)
    return keyFile
  }

  function remove(privateKeyId) {
    const next = { ...entries.value }
    delete next[String(privateKeyId)]
    entries.value = next
    writeRaw(next)
  }

  function clear() {
    entries.value = {}
    writeRaw({})
  }

  /** 导出整个密钥环（备份用）。格式与单个密钥文件一致，便于逐个再导入。 */
  function exportAll() {
    return Object.values(entries.value).map((item) => serializeKeyFile(item))
  }

  /** 当前密钥环里所有条目的摘要（**不含私钥**），用于列表展示与核对 */
  const summaries = computed(() =>
    Object.values(entries.value).map((item) => ({
      keyId: item.key_id,
      userId: item.user_id,
      algorithm: item.algorithm,
      createdAt: item.created_at,
      publicKey: item.public_key,
      kind: item.kind || KEY_FILE_KIND
    }))
  )

  return { entries, size, summaries, has, get, importKeyFile, remove, clear, exportAll }
})

export default useKeyringStore