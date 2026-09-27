# 文档索引

> 最后更新：2026-09-26（随代码清理整理）
>
> `doc/` 下混着**现行文档**与**历史记录**。本索引把它们分开，
> 新读者按第一段顺序读即可，第二段只在需要追溯时看。

---

## 一、现行文档（反映当前实现）

| 文档 | 内容 |
|---|---|
| `project_overview.md` | 系统整体设计 |
| `message-protocol.md` | 服务间通信协议 |
| `docker-runbook.md` | 部署与运维 |
| `frontend-role-boundary.md` | 前端角色边界（含 D9 决策） |
| `fisco-chain-and-node-page-runbook.md` | 节点管理页与 FISCO 链运维 |
| `blockchain-runtime.md` | 链上运行时 |
| `three-subsystem-refactor-plan.md` | 三子系统重构方案（**设计稿，未实施**） |
| `kms-restructure-plan.md` | 重构计划（大量决策记录，仍被引用） |
| `security-test-plan.md` | 安全测试方案 |
| `key-generation-test-description.md` | 密钥生成测试说明 |
| `expected-results-phrases.md` | 预期结果措辞 |
| `load-test-report-template.md` | 压测报告模板 |
| `user-permission-implementation.md` | 权限实现（注：权限审批流已在重构方案中列为待删） |
| `retired-generate-frontend.md` | `/generate/` 前端退役理由（原 `kms-generate/front/RETIRED.md`） |
| `assets/` | 图片与静态资源（含 `kms_architecture.html`） |

---

## 二、历史记录（不代表当前实现）

| 文档 | 为什么保留 |
|---|---|
| `legacy-project_overview.md` | 拆分前的系统概览 |
| `kms-split-implementation-plan.md` | 当初做子系统拆分时的实施计划 |
| `java-ruoyi-repair-guide.md` | RuoYi 修复记录 |
| `kms-agent-task-breakdown.md` | 阶段性任务拆分 |
| `pqkds-demo-migration-execution-plan.md` | PQKDS demo 迁入方案 |

> 这些文档里的**路径引用可能已失效**——2026-09-26 的代码清理删除了
> `legacy-kms/`、`legacy-kms-go/`、`kms-generate/front/`、
> `kms-distribute/java-backend/` 等目录，并把
> `kms-distribute/extracted/ruoyi (2)/` 改名为 `kms-distribute/dvadmin/`。
>
> 需要查阅已删目录时用回滚点：
> `git checkout pre-cleanup-20260926 -- <路径>`

---

## 三、其他位置的文档

| 位置 | 内容 |
|---|---|
| `README.md`（仓库根） | 仓库结构与快速入口 |
| `kms-ops/README.md` | 部署编排说明 |
| `kms-generate/docs/migration-map.md` | 代码迁移映射表；其"一、系统边界概述"一节说明了各子系统的职责划分，仍有参考价值 |
| `kms-{user,generate,updatedel,distribute,acceptance}/README.md` | 各子系统自己的说明 |