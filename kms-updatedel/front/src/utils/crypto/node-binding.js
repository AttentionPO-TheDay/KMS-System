/**
 * 节点登录**绑定文件**（本机）。
 *
 * 是什么
 * ------
 * 每次节点登录成功后，本机（IndexedDB）写下/刷新一份**绑定记录**：
 *
 *     k: "node-<节点编号>-binding"                        ← meta store 主键
 *     {
 *       name:     "node-<节点编号>-binding",              ← 记录名（key-ref 定义）
 *       nodeId:   "<节点编号>",
 *       nodeName: "<节点显示名>",                          ← 登录响应里的 name
 *       deviceFingerprint: "<32 位十六进制>",              ← 设备公钥指纹（§4.4）
 *       createdAt:      "2026-10-08T...+08:00",           ← 首次登录（此后固定）
 *       lastLoginAt:    "2026-10-08T...+08:00",           ← 最近一次登录
 *       loginCount:     3,
 *     }
 *
 * 记录里**没有任何秘密**：设备私钥在 `deviceKeys` store（不可导出），
 * 指纹是公开量。绑定文件的作用只有两条：
 *   * 回答"这台浏览器现在的绑定是哪个节点、绑在哪台设备上"（「本地密钥环境」页）；
 *   * 记录**最近一次登录**，让"换节点"这件事在界面上可见可确认。
 *
 * 为什么一个浏览器只留一份
 * ------------------------
 * 文档 §4 允许一个浏览器托管多个节点身份（同一台开发机测试多个节点）。
 * 但**登录这个动作本身是有归属的**：本机服务的是最后登录的那个节点。
 * 所以策略是：
 *
 *   * 登录**同一个**节点 → 刷新这一份（首登时间不动、`loginCount` +1）；
 *   * 登录/激活**另一个**节点 → 删掉旧的那一份（以及旧节点的**设备凭据**），
 *     只留新的。
 *
 * ⚠️ 被删掉的是"旧节点在这台设备上的登录身份"。删了之后该节点要在这台
 *    浏览器上重新登录，只能由管理员重签激活凭证（设备公钥还登记在服务端，
 *    本机私钥没了就签不出挑战）—— 调用方**必须先征得确认**再做。
 *    所以这里只提供 `clearOtherBindings()`，它由登录页在用户确认后调用，
 *    而不是登录流程里的自动副作用。
 *
 * 与设备凭据（`node-{id}-device-auth`）的关系
 * ------------------------------------------
 * 绑定文件是**记录**，设备凭据是**身份**。删绑定 = 连同该节点的设备凭据一起
 * 清掉（见 `clearOtherBindings`），否则会出现"没有绑定文件、却还能登录"的
 * 半截状态 —— 那正是"绑定文件说本机没有这个节点，点一下却进去了"的悖论。
 */

import {
  readMetaRecord,
  writeMetaRecord,
  deleteMetaRecord,
  listMetaRecords,
} from './node-key-store.js'
import { buildBindingRecord, parseBindingRecord } from './key-ref.js'
import {
  deviceFingerprint,
  hasDeviceKey,
  listActivatedNodes,
  removeDeviceKey,
} from './device-credential.js'
import { IS_DEMO } from '../entry-mode.js'

/**
 * 绑定记录的 meta 主键。
 *
 * 记录名（`node-{id}-binding`）本身就是 store 里唯一的键前缀 —— 不需要再
 * 叠一层 `binding:`：绑定的候选集合由 `parseBindingRecord` 判（它对任何
 * `-binding` 结尾的写法都认），而 meta store 里其它记录（`protector` /
 * `deviceId`）都不以 `node-` 开头，两不相扰。
 *
 * ⚠️ 曾经写成 `binding:` + 记录名，结果记录里出现
 *    `node-Node-001-binding-binding`（前缀一次、后缀又一次）——
 *    功能不受影响，但人的第一反应是"这串是不是拼错了"，
 *    而真正该被信任的解析器反而像没生效。
 */
export function bindingKey(nodeId) {
  return buildBindingRecord(nodeId)
}

/** 读本机某节点的绑定文件；没有返回 null。形状见文件头。 */
export async function readBinding(nodeId) {
  const id = String(nodeId ?? '').trim()
  if (!id) {
    return null
  }
  try {
    const record = await readMetaRecord(bindingKey(id))
    if (!record || !record.nodeId) {
      return null
    }
    return normalize(record)
  } catch {
    // 密钥库不可用（隐私模式 / 禁用 IndexedDB）按"没有绑定"处理：
    // 调用方据此显示"本机还没有绑定"，而不是整页打不开。
    return null
  }
}

/**
 * 列出本机全部绑定文件（新登录的在前）。
 *
 * ⚠️ 用 `parseBindingRecord` 过滤，**不是**前缀匹配：meta store 里还住着
 *    保护密钥（`protector`）与设备标识（`deviceId`），一旦按"前缀像不像"
 *    去猜，往后新增 meta 记录时列表里就会冒出莫名其妙的一条 —— 且不报错。
 *    解析器只认 `node-{id}-binding`，别的形状一律返回 null。
 */
export async function listBindings() {
  try {
    const records = await listMetaRecords('')
    return records
      .map(normalize)
      .filter((b) => b.nodeId && parseBindingRecord(b.name))
      .sort((a, b) => String(b.lastLoginAt || '').localeCompare(String(a.lastLoginAt || '')))
  } catch {
    return []
  }
}

/**
 * 本机当前绑定（最近登录的那一份）；没有返回 null。
 *
 * 「当前」的口径是 `lastLoginAt` 最新的那一份 —— 与登录流程写入的时机一致。
 * 正常情况下 `listBindings()` 长度至多 1（换节点会清旧的），多份只可能是
 * 历史遗留（例如本功能上线前激活过的节点），取最新的那一份仍是正确语义。
 */
export async function currentBinding() {
  const all = await listBindings()
  return all.length ? all[0] : null
}

/**
 * 记录一次成功的节点登录：写下或刷新绑定文件。
 *
 * @param {string} nodeId 节点**业务编号**（如 `Node-001`）；写不出合法记录名时返回 null
 * @param {object} [info]
 * @param {string} [info.name]   节点显示名（登录响应里的 `name`）
 * @param {string} [info.deviceFingerprint] 设备公钥指纹；缺省现算
 * @returns {Promise<object|null>} 落库后的记录（形状见文件头）
 *
 * ⚠️ 本函数**不抛**：绑定是登录成功之后的记账，记不上不该把一次已经成立的
 *    登录判成失败（令牌都发下来了）。失败只记 console.warn，调用方照常进站。
 */
export async function recordNodeLogin(nodeId, info = {}) {
  const id = String(nodeId ?? '').trim()
  if (!id) {
    return null
  }
  try {
    const now = new Date().toISOString()
    const existing = await readBinding(id)
    const fingerprint = String(
      info.deviceFingerprint ?? (await deviceFingerprint(id)) ?? ''
    ).trim()
    const record = {
      k: bindingKey(id),
      name: buildBindingRecord(id),
      nodeId: id,
      // 显示名可能为空（登录响应没给）——沿用已有记录的，避免被空串覆盖。
      nodeName: String(info.name ?? '').trim() || existing?.nodeName || '',
      deviceFingerprint: fingerprint,
      // 首次登录时间**沿用已有**：它回答"这台设备从什么时候起绑的"，
      // 每次登录都刷新的话这个问题就永远只有"刚刚"一个答案。
      createdAt: existing?.createdAt || now,
      lastLoginAt: now,
      loginCount: Number(existing?.loginCount || 0) + 1,
    }
    await writeMetaRecord(record)
    return normalize(record)
  } catch (error) {
    console.warn('[node-binding] 写入绑定文件失败：', error?.message || error)
    return null
  }
}

/** 删掉某节点的绑定文件（**只删记录**；设备凭据见 `clearOtherBindings`）。 */
export async function removeBinding(nodeId) {
  const id = String(nodeId ?? '').trim()
  if (!id) {
    return
  }
  await deleteMetaRecord(bindingKey(id))
}

/**
 * 清除**其它**节点的绑定与登录身份，只留 `keepNodeId`。
 *
 * 做了什么（逐项都要做，少一项就是半截状态）：
 *   1. 删掉其它节点的绑定文件；
 *   2. 删掉其它节点的设备凭据（`node-{id}-device-auth` 及其公钥副本）——
 *      这是"登录身份"，留着它，本机就仍然能以那个节点的身份登录；
 *   3. 对**没有绑定文件但仍有设备凭据**的节点同样处理（本功能上线前激活的
 *      存量浏览器走的正是这条）—— 判据是凭据本身，不是绑定文件。
 *
 * ⚠️ 不碰 `keepNodeId` 的任何东西。也不碰其它节点的**长期密钥材料**
 *    （`node/...` 那些）—— 那是分发用的，不属于"登录绑定"。
 *    清不清它由用户自己决定（「本地密钥环境」页的重置入口）。
 *
 * @param {string} keepNodeId 要保留的节点编号（留空 = 全清）
 * @param {{removeDeviceCredentials?: boolean}} [options]
 *   `removeDeviceCredentials: false` 可只删绑定记录、保留登录身份（默认 true）。
 *   默认值就是"换节点"该有的语义：不保留旧的登录身份。
 * @returns {Promise<{bindingsRemoved: string[], credentialsRemoved: string[]}>}
 */
export async function clearOtherBindings(keepNodeId, options = {}) {
  if (IS_DEMO) return { bindingsRemoved: [], credentialsRemoved: [] }
  const keep = String(keepNodeId ?? '').trim()
  const removeCredentials = options.removeDeviceCredentials !== false
  const result = { bindingsRemoved: [], credentialsRemoved: [] }

  try {
    const bindings = await listBindings()
    for (const binding of bindings) {
      if (binding.nodeId === keep) {
        continue
      }
      await removeBinding(binding.nodeId)
      result.bindingsRemoved.push(binding.nodeId)
    }
  } catch (error) {
    console.warn('[node-binding] 清除旧绑定失败：', error?.message || error)
  }

  if (!removeCredentials) {
    return result
  }

  // ⚠️ 判据取**设备凭据列表**而不是绑定列表：本功能上线前激活的浏览器
  //    只有凭据、没有绑定文件，只按绑定删的话它们会被漏掉 —— 而"漏掉"
  //    的表现正是"换了节点，旧节点却还能点进去登录"。
  try {
    for (const nodeId of await listActivatedNodes()) {
      if (nodeId === keep) {
        continue
      }
      await removeDeviceKey(nodeId)
      result.credentialsRemoved.push(nodeId)
      // 认得出身份却签不出名的残状态：凭据在、但已经不能用（索引损坏等）。
      // 一并清掉绑定记录，免得列表上留一条点不动的条目。
      if (!result.bindingsRemoved.includes(nodeId)) {
        await removeBinding(nodeId)
        result.bindingsRemoved.push(nodeId)
      }
    }
  } catch (error) {
    console.warn('[node-binding] 清除旧设备凭据失败：', error?.message || error)
  }

  return result
}

/**
 * 本机是否还有该节点的**可用登录身份**（设备凭据在且能签）。
 * 供页面判断"绑定文件说绑定在，实际能不能登录"。
 */
export async function hasLoginIdentity(nodeId) {
  return hasDeviceKey(nodeId)
}

// ---------------------------------------------------------------------------
// 内部：记录归一
// ---------------------------------------------------------------------------
// 读出来的记录可能是历史版本（字段缺失），调用方拿到的形状必须一致 ——
// 让每个页面各写一遍兜底，迟早在某个页面上漏一个字段。

function normalize(record) {
  const parsed = parseBindingRecord(String(record?.name || ''))
  const nodeId = String(record?.nodeId || parsed?.nodeId || '').trim()
  return {
    nodeId,
    name: String(record?.name || (nodeId ? buildBindingRecord(nodeId) : '')),
    nodeName: String(record?.nodeName || ''),
    deviceFingerprint: String(record?.deviceFingerprint || ''),
    createdAt: record?.createdAt || '',
    lastLoginAt: record?.lastLoginAt || '',
    loginCount: Number(record?.loginCount || 0),
  }
}
