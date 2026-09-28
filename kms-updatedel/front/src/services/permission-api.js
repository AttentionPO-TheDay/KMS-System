/**
 * 权限项元数据（`permissionFeatures`）。
 *
 * ⚠️ 本模块在阶段 8/9 被**大幅收窄**：原先它还有一整套"申请-审批"的调用
 * （`submitPermissionRequest` / `listPermissionRequests` /
 * `getLatestApprovedTemporaryRequest` / `rollbackPermission`），
 * 全部指向 `kms-generate` 的 `/permission/request/*` 接口。
 *
 * 那套东西在阶段 8 被整体删除 —— 理由写在重构文档里：
 * 节点权限由 `principal_type + permission_level + 资源属主` **直接决定**，
 * 临时审批流不再承担真实授权作用，继续保留只会形成第二套权限语义。
 *
 * 而**接口删了、前端这四个函数还留着** —— 谁要是照着老代码调一下，
 * 会拿到一个 404，却完全看不出"这个功能已经被有意去掉了"。
 * 所以一并删掉，只留下仍然被使用的常量。
 *
 * 现在唯一的使用方是工作台（`views/workbench/index.vue`），
 * 它用 `permissionFeatures.AUTO_UPDATE.label` 做展示文案。
 */

import { apiBases } from '@/config/api-bases'

/**
 * 可申请的权限项。
 *
 * D1：用户侧 `PUBLIC_KEY_LIST`（查看公共密钥列表）已**整功能删除** ——
 * 该功能会让一个用户看到其他用户的公钥集合，与「密钥不外泄」的目标冲突。
 *
 * 因此现在只剩 `AUTO_UPDATE` 一项，且**只用于取标签文案**：
 * 真正的权限判定在服务端按 `permission_level` 做，不经过这里。
 */
export const permissionFeatures = {
  AUTO_UPDATE: {
    system: 'lifecycle',
    label: '密钥自动更新',
    requestLevel: 0,
    apiBase: apiBases.lifecycleApi
  }
}