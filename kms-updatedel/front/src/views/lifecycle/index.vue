<template>
  <section class="page lifecycle-page">

    <article class="panel">
      <div class="panel-head header-actions">
        <div class="identity-line">
          <strong>{{ profile.userName || '未登录' }}</strong>
          <el-tag size="small" type="info">{{ roleText(profile.roleLevel) }}</el-tag>
        </div>
        <el-button @click="reloadCurrentTab">刷新当前页</el-button>
      </div>
    </article>

    <div class="lifecycle-dashboard">
      <nav class="inner-sidenav">
        <div class="nav-item" :class="{ active: activeTab === 'mykeys' }" @click="activeTab = 'mykeys'">
          <el-icon class="icon"><Key /></el-icon> 我的密钥库
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'autoupdate' }" @click="activeTab = 'autoupdate'">
          <el-icon class="icon"><Lightning /></el-icon> 自动更新配置
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'results' }" @click="activeTab = 'results'">
          <el-icon class="icon"><Download /></el-icon> 操作结果回执
        </div>
      </nav>

      <main class="inner-main-content">
        <!-- Floating Action Bar -->
        <transition name="fade-slide">
          <div v-if="activeTab === 'mykeys' && selectedIds.length > 0" class="floating-action-bar">
            <span class="selection-count">已选择 {{ selectedIds.length }} 项</span>
            <div class="fab-actions">
              <el-button type="success" :disabled="selectedIds.length !== 1" @click="openUpdateDialog()">操作更新</el-button>
              <el-button type="danger" @click="handleRevoke()">KMS引用回收</el-button>
            </div>
          </div>
        </transition>

        <div v-show="activeTab === 'mykeys'" class="tab-pane relative-pane">
          <article class="panel">
          <el-form :model="myKeyQuery" inline label-width="88px" class="query-form">
            <el-form-item label="密钥名称">
              <el-input v-model="myKeyQuery.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="searchMyKeys" />
            </el-form-item>
            <el-form-item label="算法名称">
              <el-input v-model="myKeyQuery.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="searchMyKeys" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="searchMyKeys">搜索</el-button>
              <el-button @click="resetMyKeys">重置</el-button>
            </el-form-item>
          </el-form>

          <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

          <el-table v-loading="myKeysLoading" :data="myKeys" @selection-change="handleSelectionChange">
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="密钥 ID" align="center" prop="keyId" width="90" />
            <el-table-column label="用户名" align="center" prop="userName" width="120" />
            <el-table-column label="算法类型" align="center" prop="encrytType" min-width="140" />
            <el-table-column label="算法名称" align="center" prop="encrytName" width="120" />
            <!-- 版本列（2026-09-24 新增）：轮换会让版本 +1，列表里能直接看出哪把密钥
                 被轮换过；更迭过程（哪一版由手动/自动、对应哪笔链上交易）见「详情 → 版本更迭」。 -->
            <el-table-column label="版本" align="center" width="80">
              <template #default="scope">
                <el-tag size="small" :type="Number(scope.row.version || 1) > 1 ? 'warning' : 'info'">
                  v{{ scope.row.version ?? 1 }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="密钥名称" align="center" prop="keyName" min-width="150" />
            <el-table-column label="密钥用途" align="center" prop="keyUse" min-width="150" show-overflow-tooltip />
            <el-table-column label="自动更新" align="center" width="110">
              <template #default="scope">
                <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
                  {{ autoUpdateText(scope.row.autoUpdate) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="上链状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="chainStatusType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" align="center" prop="updTime" width="180" />
            <el-table-column label="操作" align="center" width="260" fixed="right">
              <template #default="scope">
                <el-button link type="primary" :disabled="isRevoked(scope.row.status)" @click="openUpdateDialog(scope.row)">
                  更新
                </el-button>
                <el-button link type="danger" :disabled="isRevoked(scope.row.status)" @click="handleRevoke(scope.row)">
                  KMS引用回收
                </el-button>
                <el-button link type="warning" @click="openAnalysisDialog(scope.row)">安全分析</el-button>
                <el-button link @click="showDetail(scope.row.keyId)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="myKeyTotal > 0"
            :total="myKeyTotal"
            v-model:page="myKeyQuery.pageNum"
            v-model:limit="myKeyQuery.pageSize"
            @pagination="loadMyKeys"
          />
        </article>
        </div>

        <div v-show="activeTab === 'autoupdate'" class="tab-pane relative-pane">
          <!-- D2：原独立的「权限管理」页已删除，申请入口收敛到本页。
               权限不足时不再把人送去另一个页面，直接在本页弹窗提交。 -->
          <div class="permission-bar">
            <div class="permission-bar-text">
              <strong>自动更新权限</strong>
</div>
            <div class="permission-bar-actions">
              <el-tag size="small" :type="canManageAutoUpdate ? 'success' : 'info'" effect="light">
                {{ canManageAutoUpdate ? (showAutoUpdateRollback ? '已具备（临时权限）' : '已具备') : '未具备' }}
              </el-tag>
              <el-button
                type="primary"
                :disabled="canManageAutoUpdate"
                @click="openPermissionDialog"
              >
                {{ canManageAutoUpdate ? '无需申请' : '申请自动更新权限' }}
              </el-button>
              <el-button v-if="showAutoUpdateRollback" @click="handleRollback">回退权限</el-button>
            </div>
          </div>

          <el-alert
            v-if="!canManageAutoUpdate"
            title="当前账号没有生命周期域自动更新配置的权限，请点击上方「申请自动更新权限」提交申请。"
            type="warning"
            :closable="false"
            show-icon
            class="mb12"
          />

          <el-alert
            v-if="showAutoUpdateRollback"
            title="当前自动更新配置权限为临时权限，完成配置后建议立即回退。"
            type="info"
            :closable="false"
            show-icon
            class="mb12"
          >
            <template #default>
              <el-button type="primary" link @click="handleRollback">回退权限</el-button>
            </template>
          </el-alert>

          <article class="panel">
          <!-- 权限不足时把筛选控件本身也置灰并给出原因，
               避免出现「控件可用但按钮禁用」的困惑（此前只有上方一条 alert，
               用户滚动后看不到原因，会误以为功能损坏）。 -->
          <el-form :model="autoUpdateQuery" inline label-width="88px" class="query-form">
            <el-form-item label="密钥名称">
              <el-tooltip
                :disabled="canManageAutoUpdate"
                content="需要「密钥自动更新」权限，请点击上方「申请自动更新权限」"
                placement="top"
              >
                <el-input
                  v-model="autoUpdateQuery.keyName"
                  placeholder="请输入密钥名称"
                  clearable
                  :disabled="!canManageAutoUpdate"
                  @keyup.enter="searchAutoUpdate"
                />
              </el-tooltip>
            </el-form-item>
            <el-form-item label="自动更新">
              <el-tooltip
                :disabled="canManageAutoUpdate"
                content="需要「密钥自动更新」权限，请点击上方「申请自动更新权限」"
                placement="top"
              >
                <el-select
                  v-model="autoUpdateQuery.autoUpdate"
                  placeholder="全部"
                  clearable
                  :disabled="!canManageAutoUpdate"
                >
                  <el-option label="已开启" value="1" />
                  <el-option label="已关闭" value="0" />
                </el-select>
              </el-tooltip>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :disabled="!canManageAutoUpdate" @click="searchAutoUpdate">搜索</el-button>
              <el-button :disabled="!canManageAutoUpdate" @click="resetAutoUpdate">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="autoUpdateLoading" :data="autoUpdateKeys">
            <el-table-column label="密钥 ID" align="center" prop="keyId" width="90" />
            <el-table-column label="用户名" align="center" prop="userName" width="120" />
            <el-table-column label="算法类型" align="center" prop="encrytType" min-width="140" />
            <el-table-column label="密钥名称" align="center" prop="keyName" min-width="150" />
            <el-table-column label="状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="自动更新状态" align="center" width="120">
              <template #default="scope">
                <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
                  {{ autoUpdateText(scope.row.autoUpdate) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" align="center" prop="updTime" width="180" />
            <el-table-column label="操作" align="center" width="160" fixed="right">
              <template #default="scope">
                <el-button
                  link
                  type="primary"
                  :disabled="isRevoked(scope.row.status)"
                  @click="toggleAutoUpdate(scope.row)"
                >
                  {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '关闭' : '开启' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="autoUpdateTotal > 0"
            :total="autoUpdateTotal"
            v-model:page="autoUpdateQuery.pageNum"
            v-model:limit="autoUpdateQuery.pageSize"
            @pagination="loadAutoUpdateKeys"
          />
        </article>
        </div>

        <div v-show="activeTab === 'results'" class="tab-pane relative-pane">
          <article class="panel">
            <el-form :model="resultQuery" inline label-width="88px" class="query-form">
              <el-form-item label="操作类型">
                <el-select v-model="resultQuery.actionType" placeholder="全部" clearable>
                  <el-option label="密钥更新" value="UPDATE" />
                  <el-option label="KMS引用回收" value="REVOKE" />
                </el-select>
              </el-form-item>
              <el-form-item label="接收状态">
                <el-select v-model="resultQuery.receiveStatus" placeholder="全部" clearable>
                  <el-option label="未接收" value="0" />
                  <el-option label="已接收" value="1" />
                </el-select>
              </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="searchResults">搜索</el-button>
              <el-button @click="resetResults">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="resultLoading" :data="resultList">
            <el-table-column label="记录ID" prop="recordId" width="90" />
            <el-table-column label="密钥ID" prop="keyId" width="90" />
            <el-table-column label="密钥名称" prop="keyName" min-width="140" />
            <el-table-column label="操作类型" width="110">
              <template #default="scope">{{ actionTypeText(scope.row.actionType) }}</template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="scope">{{ actionSourceText(scope.row.actionSource) }}</template>
            </el-table-column>
            <el-table-column label="结果" width="100">
              <template #default="scope">
                <el-tag :type="resultStatusType(scope.row.resultStatus)">{{ resultStatusText(scope.row.resultStatus) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="接收状态" width="110">
              <template #default="scope">
                <el-tag :type="receiveStatusType(scope.row)">{{ receiveStatusText(scope.row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="结果说明" prop="resultMessage" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作时间" width="180">
              <template #default="scope">{{ formatDateTime(scope.row.actionTime) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="scope">
                <el-button link @click="showDetail(scope.row.keyId)">详情</el-button>
                <el-button
                  v-if="scope.row.receiveStatus !== '1' && scope.row.resultStatus !== '0'"
                  link
                  type="primary"
                  @click="receiveResult(scope.row)"
                >接收</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="resultTotal > 0"
            :total="resultTotal"
            v-model:page="resultQuery.pageNum"
            v-model:limit="resultQuery.pageSize"
            @pagination="loadResultList"
          />
        </article>
        </div>
      </main>
    </div>

    <el-dialog v-model="updateDialogOpen" title="密钥更新" width="520px" append-to-body>
      <el-form ref="updateFormRef" :model="updateForm" :rules="updateRules" label-width="96px">
        <el-form-item label="密钥 ID">
          <el-input :model-value="String(updateForm.keyId || '')" disabled />
        </el-form-item>
        <el-form-item label="算法类型">
          <el-input v-model="updateForm.encrytType" disabled />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input v-model="updateForm.encrytName" disabled />
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="updateForm.keyName" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="updateForm.keyUse" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain">
          <el-input v-model="updateForm.keyDomain" maxlength="64" clearable />
        </el-form-item>
        <!--
          手动密钥轮换（2026-09-24 新增；阶段 4 改为部分刷新）。
          后端按请求里**显式声明的 `rotate`** 分流：
            * false / 不给 → updateMetadata：只改 名称/用途/所属域，**版本不变、不写链**；
            * true        → rotateKey：KGC 重新签发部分密钥、**版本 +1**、链上写 rotateKey。
          这里原来还有一段注释说明旧判据（"有没有带 uA"）以及它带来的问题，
          已随判据一起删除 —— 旧判据在部分刷新下必然失效，因为 §5.3 要求
          更新时 uA **保持不变**，请求里带的正是与库中相同的那个值。
        -->
        <el-form-item label="密钥轮换">
          <div class="rotation-box">
            <el-switch
              v-model="rotateRequested"
              :disabled="updateSubmitting"
              active-text="刷新密钥材料"
              inactive-text="仅改元数据"
            />
            <!--
              文档 §5.3：SM2 / SSCL 的更新是**部分刷新** —— 节点侧秘密 u 与公开量 uA
              保持不变，只让 KGC 重新生成随机 w 和部分密钥。

              这里原来有一个「重新生成本地密钥材料」按钮，它造的是**新的 u 和新的 uA**，
              与 §5.3 描述的不是同一个协议：那样虽然也能得到一份可用的新密钥，
              但节点侧秘密跟着换了，等于换了一把密钥而不是"更新"。改成部分刷新后，
              本机只需要**现有的**私钥文件，u 从头到尾不动。
            -->
            <el-tag size="small" type="warning">部分刷新（uA 保持不变）</el-tag>
            <span class="rotation-hint">版本 {{ versionBefore }} → {{ versionAfter }}</span>
            <div v-if="rotationAvailable" class="rotation-ready">
              <span class="muted">将用本机密钥环中的私钥合成新版本 d_A</span>
              <span class="mono">{{ shortUa(rotationMaterial.publicKey) }}</span>
            </div>
            <!--
              ⚠️ 节点侧秘密 u 与合成后的 d_A **全程不出浏览器**（R1' 红线）。
              轮换后本机密钥环里的密钥文件会就地更新，因此不需要再让用户手工抄一份
              —— 这正是部分刷新相比"重新生成材料"的另一个好处：不会产生
              "旧文件还在、但已经对不上新版本"的静默错配。
            -->
            <el-alert
              v-else
              type="warning"
              :closable="false"
              show-icon
              :title="rotationBlockReason"
            />
          </div>
        </el-form-item>
        <!--
          这里原来有一个「自动更新」开关，已移除（2026-09-24 用户反馈）：
          1. 本页已经有**独立的**「自动更新配置」区域（上方 autoUpdateKeys 那张表，
             带专门的开关与筛选），这里的开关是重复入口；
          2. 它会污染更新请求 —— 提交时把开关的当前值一并带上（恒非空），
             而后端把"请求里出现 autoUpdate"当成"要改自动更新"，
             于是**只想改密钥名称**的用户会被拦下，报错是
             "当前用户没有自动更新操作权限"，与他在做的事完全对不上。
          现在更新只提交元数据字段；要改自动更新请用上方那个专门的入口。
        -->
      </el-form>
      <template #footer>
        <el-button @click="updateDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="updateSubmitting" @click="submitUpdate">确认更新</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialogOpen" title="密钥详情" width="720px" append-to-body>
      <div v-if="selectedKey" class="detail-grid">
        <p><strong>密钥 ID：</strong>{{ selectedKey.keyId }}</p>
        <p><strong>用户 ID：</strong>{{ selectedKey.userId }}</p>
        <p><strong>用户名：</strong>{{ selectedKey.userName || '-' }}</p>
        <p><strong>算法类型：</strong>{{ selectedKey.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ selectedKey.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedKey.keyName || '-' }}</p>
        <p><strong>密钥用途：</strong>{{ selectedKey.keyUse || '-' }}</p>
        <p><strong>所属域：</strong>{{ selectedKey.keyDomain || '-' }}</p>
        <p><strong>自动更新：</strong>{{ autoUpdateText(selectedKey.autoUpdate) }}</p>
        <p><strong>状态：</strong>{{ statusText(selectedKey.status) }}</p>
        <p><strong>版本：</strong>{{ selectedKey.version ?? '-' }}</p>
        <p><strong>上链状态：</strong>{{ chainStatusText(selectedKey.chainStatus) }}</p>
        <p><strong>交易哈希：</strong>{{ selectedKey.chainHash || '-' }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
      </div>

      <!--
        版本更迭轨迹（2026-09-24 新增）。
        数据来自 key_operation_record：每次轮换都会落一条记录，带 key_version /
        action_source（MANUAL·AUTO）/ chain_hash / block_height。
        详情里的"版本"只说明**当前**是第几版，看不出更迭过程；这里把历次版本列出来，
        评审要的"版本更迭"才算能自证。
      -->
      <div v-if="selectedKey" class="version-history">
        <h4>版本更迭</h4>
        <el-table
          :data="versionHistory"
          size="small"
          :empty-text="versionHistoryLoading ? '加载中…' : '暂无轮换记录（仅更新元数据不会产生版本更迭）'"
        >
          <el-table-column label="版本" width="64" align="center">
            <template #default="scope">v{{ scope.row.keyVersion ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="76" align="center">
            <template #default="scope">{{ actionTypeText(scope.row.actionType) }}</template>
          </el-table-column>
          <el-table-column label="来源" width="64" align="center">
            <template #default="scope">{{ actionSourceText(scope.row.actionSource) }}</template>
          </el-table-column>
          <el-table-column label="结果" width="80" align="center">
            <template #default="scope">{{ resultStatusText(scope.row.resultStatus) }}</template>
          </el-table-column>
          <el-table-column label="操作时间" width="160">
            <template #default="scope">{{ formatActionTime(scope.row.actionTime) }}</template>
          </el-table-column>
          <el-table-column label="交易哈希" min-width="140">
            <template #default="scope">
              <span class="mono">{{ scope.row.chainHash || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="区块高度" width="86" align="center">
            <template #default="scope">{{ scope.row.blockHeight ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <!-- 申请「密钥自动更新」权限（D2：由原「权限管理」页迁移而来）。
         只保留 AUTO_UPDATE 一项 —— PUBLIC_KEY_LIST 已按 D1 整体删除。 -->
    <el-dialog v-model="permissionDialogOpen" title="申请自动更新权限" width="520px" append-to-body>
      <p class="muted">
        开启后可为密钥配置托管自动更新。审批通过后权限为<strong>临时授权</strong>，
        完成配置后请及时回退。
      </p>
      <el-form label-position="top">
        <el-form-item label="申请理由" required>
          <el-input
            v-model="permissionReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="请简述开启安全托管的原因，至少 4 个字符"
          />
        </el-form-item>
      </el-form>
      <p v-if="permissionError" class="error-text">{{ permissionError }}</p>
      <template #footer>
        <el-button @click="permissionDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="permissionSubmitting" @click="submitPermission">
          提交审批申请
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="analysisDrawerOpen" title="密钥防线全息扫描结果" size="65%">
      <div v-if="analysisLoading" class="analysis-loading" style="text-align: center; padding: 40px;">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在拉取源端底层数据，请稍候...</p>
      </div>
      <div v-else-if="analysisResult" class="analysis-content">
        <h3 style="margin-top:0;">1. 嫌疑面报表 (Base Info)</h3>
        <el-descriptions border :column="2" style="margin-bottom: 20px;">
          <el-descriptions-item label="密钥ID">{{ analysisResult.baseInfo?.keyId }}</el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ analysisResult.baseInfo?.keyName }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ analysisResult.baseInfo?.encrytName }}</el-descriptions-item>
          <el-descriptions-item label="使用域">{{ analysisResult.baseInfo?.keyDomain }}</el-descriptions-item>
          <el-descriptions-item label="版本号">{{ analysisResult.baseInfo?.version }}</el-descriptions-item>
          <el-descriptions-item label="安全状态">
            <el-tag :type="statusTagType(analysisResult.baseInfo?.status)">{{ statusText(analysisResult.baseInfo?.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="链上哈希证实" :span="2">{{ analysisResult.baseInfo?.chainHash || '尚未存证' }}</el-descriptions-item>
        </el-descriptions>

        <h3>2. 历史分发存留溯源 (Distribute Footprints)</h3>
        <el-table :data="analysisResult.distributeFootprints" border stripe style="width: 100%; margin-bottom: 20px;" max-height="250">
          <el-table-column prop="user_name" label="下发终端实体"></el-table-column>
          <el-table-column label="分发类型">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_type == '1'" type="info">初始分发</el-tag>
                <el-tag v-else-if="scope.row.distribute_type == '2'" type="warning">自动更新分发</el-tag>
                <el-tag v-else type="danger">补发</el-tag>
             </template>
          </el-table-column>
          <el-table-column prop="distribute_time" label="下达时间"></el-table-column>
          <el-table-column label="缓存状态" width="120">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_status == '2'" type="danger">该节点持有缓存!</el-tag>
                <el-tag v-else type="success">未接收成功</el-tag>
             </template>
          </el-table-column>
        </el-table>

        <h3>3. 异常操作轨迹盘点 (Timeline Trails)</h3>
        <el-timeline style="padding-left: 10px;">
          <el-timeline-item
            v-for="(op, index) in analysisResult.operationTrails"
            :key="index"
            :timestamp="op.action_time ? formatDateTime(op.action_time) : '-'"
            :type="op.action_type === 'REVOKE' ? 'danger' : 'primary'"
            :color="op.result_status == '1' ? 'var(--kms-success)' : 'var(--kms-border-strong)'"
          >
            <strong>{{ actionTypeText(op.action_type) }}</strong> 
            操作来源: [{{ op.action_source }}]
          </el-timeline-item>
          <el-timeline-item v-if="!analysisResult.operationTrails?.length" timestamp="暂无记录">
            该密钥暂无操作流转痕迹
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
// 统一使用 Element 图标，替代此前的 emoji
import { Key, Lightning, Download } from '@element-plus/icons-vue'
// 阶段 8：审批流已整体下线，不再从 permission-api 引入任何东西。
// 该模块本身保留（另有页面引用 permissionFeatures 等常量），
// 但本页不再调用任何会打到已删接口的函数。
import {
  getLifecycleKey,
  getLifecycleKeyAnalysis,
  listLifecycleKeys,
  listLifecycleOperationRecords,
  receiveLifecycleOperationRecord,
  revokeLifecycleKey,
  updateLifecycleAutoUpdate,
  updateLifecycleKey
} from '@/services/lifecycle-api'
// SSCL 的部分刷新要在本机做拉格朗日插值，需要 KGC 公开的公共参数。
// 这个接口属于密钥生成子系统（参数是全局的），从那边取 —— 不重复实现一份。
import { getCommonParams } from '@/services/generate-api'
import { apiBases } from '@/config/api-bases'
import useUserStore from '@/store/modules/user'
import { isAdminLevel, roleLevelText } from '@/utils/role'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
// 手动轮换要重新生成本地密钥材料，用的是与「密钥生成」页同一套算法实现，
// 保证两边产生的 uA 形态一致（否则后端曲线点校验会拒）。
// 阶段 4：本页不再用 gm-crypto 生成密钥对。
// 部分刷新不需要新的 u —— 它要的正是**守住**现有的 u，所以 `SM2.generateKeyPair()`
// 及其导入一并移除。合成新 d_A 的曲线运算在 `utils/cl-key.js` 里，本页只调用它。
import { composeUpdatedPrivateKey } from '@/utils/cl-key'
import { buildKeyFile, serializeKeyFile } from '@/utils/key-file'
import useKeyringStore from '@/store/modules/keyring'

const { proxy } = getCurrentInstance()
const router = useRouter()
const userStore = useUserStore()
// 阶段 4（§5.3）：部分刷新要用本机密钥环里**这条密钥自己的**私钥来合成新版本，
// 因此这个页面也依赖密钥环 —— 它不再是"只在解密时才用得到"的东西。
const keyring = useKeyringStore()

const apiBase = apiBases.lifecycleApi
const activeTab = ref('mykeys')
const errorMessage = ref('')

const analysisDrawerOpen = ref(false)
const analysisLoading = ref(false)
const analysisResult = ref(null)

async function openAnalysisDialog(row) {
  const keyId = row?.keyId || selectedIds.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning('请先选择一条密钥记录')
    return
  }
  analysisDrawerOpen.value = true
  analysisLoading.value = true
  analysisResult.value = null
  try {
    const res = await getLifecycleKeyAnalysis(keyId)
    if (res.code === 200 || res.code === '200' || res.data) {
      analysisResult.value = res.data || res.baseInfo ? (res.data || res) : null
    } else {
      ElMessage.error(res.msg || '获取关联分析失败')
    }
  } catch (err) {
    ElMessage.error(err.message || '网络请求失败')
  } finally {
    analysisLoading.value = false
  }
}

const profile = reactive({
  userId: '',
  userName: '',
  roleLevel: 2
})

const myKeys = ref([])
const myKeysLoading = ref(false)
const myKeyTotal = ref(0)
const selectedIds = ref([])

const myKeyQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: '',
  keyName: '',
  encrytName: ''
})

const autoUpdateKeys = ref([])
const autoUpdateLoading = ref(false)
const autoUpdateTotal = ref(0)
const autoUpdateQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: '',
  keyName: '',
  autoUpdate: ''
})

const updateDialogOpen = ref(false)
const updateSubmitting = ref(false)
const updateFormRef = ref(null)
const updateForm = reactive({
  keyId: null,
  encrytType: '',
  encrytName: '',
  keyName: '',
  keyUse: '',
  keyDomain: '',
  // 仅用于显示"版本更迭：N → N+1"，不参与提交
  version: null
  // 不再有 autoUpdateEnabled：自动更新改由本页「自动更新配置」区域单独操作，
  // 更新弹窗只负责元数据（见模板里的说明）。
})

// ---------------------------------------------------------------------------
// 手动轮换 —— 阶段 4 起改为**部分刷新**（文档 §5.3）
// ---------------------------------------------------------------------------
// §5.3：SM2 / SSCL 更新时节点侧秘密 u 与公开量 uA 保持不变，只由 KGC 重新生成
// 随机 w 与部分密钥。所以这里**不再生成本地材料**，而是改用密钥环里已有的私钥
// 去合成新版本的 d_A。
//
// 为什么这个区别重要而不是名词之争：造一份新的 u / uA 固然也能得到可用的新密钥，
// 但那把"新密钥"与旧版本在密码学上毫无关系 —— 它是一次**换钥**。
// 文档 §5.1 把生成与更新分开定义，要的正是"同一条逻辑密钥的续存"，
// 而续存的前提是节点侧那一半不变。
const rotationMaterial = reactive({
  publicKey: '',
  privateKey: '',
  generatedAt: ''
})

/**
 * 用户是否勾选了"刷新密钥材料"。
 *
 * 与 `rotationMaterial.publicKey` 分开：那个是**展示用**的 uA（取自库中，
 * 用来让用户看见"要保住的正是这个值"），一旦取不到就为空，
 * 而取不到不代表用户没勾选。把两者合成一个信号，就会出现
 * "勾了但 uA 没取到 → 静默降级成只改元数据"，正是这次要消掉的那类误判。
 */
const rotateRequested = ref(false)

/**
 * 本机是否具备做部分刷新的条件。
 *
 * 三个条件缺一不可，缺哪个就明说哪一个 —— 笼统的"无法轮换"会让人以为是后端坏了。
 */
const rotationAvailable = computed(() => {
  if (!isClAlgorithm.value) {
    return false
  }
  return Boolean(keyring.get(updateForm.keyId))
})

const rotationBlockReason = computed(() => {
  if (!isClAlgorithm.value) {
    return `${updateForm.encrytName || '该算法'} 的更新必须由节点侧重新生成密钥对（文档 §5.3）：它的私钥不在服务端，服务端无法为其产生新版本。请改用「密钥生成」新建一把。`
  }
  if (!keyring.get(updateForm.keyId)) {
    return `本机密钥环里没有密钥 ${updateForm.keyId} 的私钥文件。部分刷新要用它合成新版本，请先在「密钥生成」页导出并导入该密钥文件。`
  }
  return ''
})

/** 只有 SM2 / SSCL 走 KGC 份额协议；Kyber / Falcon 的私钥在服务端之外。 */
const isClAlgorithm = computed(() => {
  const name = String(updateForm.encrytName || '').trim().toUpperCase()
  return name === 'SM2' || name === 'SSCL'
})

async function resetRotationMaterial() {
  rotationMaterial.publicKey = ''
  rotationMaterial.privateKey = ''
  rotationMaterial.generatedAt = ''
  // 打开弹窗时把库里的 uA 显示出来 —— §5.3 要求它**保持不变**，
  // 让用户看见"要保住的正是这个值"，比只说一句"uA 不变"更能防止误解。
  if (isClAlgorithm.value && updateForm.keyId) {
    try {
      const response = await getLifecycleKey(updateForm.keyId)
      const record = response?.data
      if (record?.ua) {
        rotationMaterial.publicKey = record.ua
      }
    } catch {
      // 取不到就不显示；合成本身不依赖这个展示值（它取自服务端返回）
    }
  }
}

function shortUa(value) {
  if (!value) {
    return '-'
  }
  const text = String(value)
  return text.length > 26 ? `${text.slice(0, 20)}…${text.slice(-6)}` : text
}

const versionBefore = computed(() => updateForm.version ?? 1)
// 只在真正要轮换时才预告版本 +1。一直显示 "v1 → v2" 而实际不轮换，
// 会让人以为版本已经变了 —— 那正是"以为换了密钥、其实一个字没动"的老毛病。
const versionAfter = computed(() =>
  rotateRequested.value ? Number(versionBefore.value || 1) + 1 : Number(versionBefore.value || 1)
)

// 版本更迭轨迹：来自 key_operation_record（每次轮换一条）
const versionHistory = ref([])
const versionHistoryLoading = ref(false)

async function loadVersionHistory(keyId) {
  versionHistory.value = []
  if (!keyId) {
    return
  }
  versionHistoryLoading.value = true
  try {
    const response = await listLifecycleOperationRecords({ keyId, pageNum: 1, pageSize: 20 })
    const rows = response?.rows || response?.data?.rows || response?.data || []
    versionHistory.value = Array.isArray(rows) ? rows : []
  } catch (error) {
    // 拿不到轨迹不该挡住详情本身，但要让用户知道是这个区块没数据
    versionHistory.value = []
  } finally {
    versionHistoryLoading.value = false
  }
}
const updateRules = {
  keyName: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
  keyUse: [{ required: true, message: '请输入密钥用途', trigger: 'blur' }]
}

const selectedKey = ref(null)
const detailDialogOpen = ref(false)
const approvedAutoUpdateRequestId = ref(null)
// 「申请自动更新权限」弹窗状态（D2：由已删除的权限管理页迁移而来）
const permissionDialogOpen = ref(false)
const permissionSubmitting = ref(false)
const permissionReason = ref('')
const permissionError = ref('')
const resultList = ref([])
const resultLoading = ref(false)
const resultTotal = ref(0)

const resultQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  actionType: '',
  receiveStatus: ''
})

const hasPermanentAutoUpdateAccess = computed(() => isAdminLevel(profile.roleLevel))
const hasTemporaryAutoUpdateAccess = computed(() => Boolean(approvedAutoUpdateRequestId.value))
const canManageAutoUpdate = computed(() => hasPermanentAutoUpdateAccess.value || hasTemporaryAutoUpdateAccess.value)
const showAutoUpdateRollback = computed(() => hasTemporaryAutoUpdateAccess.value)

watch(
  () => ({
    id: userStore.id,
    name: userStore.name,
    roleLevel: userStore.roleLevel,
    token: userStore.token
  }),
  (value) => {
    profile.userId = value.id || ''
    profile.userName = value.name || ''
    profile.roleLevel = value.roleLevel ?? 2
    myKeyQuery.userId = value.id || ''
    autoUpdateQuery.userId = value.id || ''

    if (!value.token) {
      approvedAutoUpdateRequestId.value = null
      myKeys.value = []
      autoUpdateKeys.value = []
      selectedIds.value = []
    }
  },
  { immediate: true }
)

watch(activeTab, async (tab) => {
  if (tab === 'autoupdate') {
    await loadAutoUpdateKeys()
    await loadAutoUpdatePermissionState()
  }
  if (tab === 'results') {
    await loadResultList()
  }
})

onMounted(async () => {
  await ensureProfile()
  await loadMyKeys()
  if (activeTab.value === 'autoupdate') {
    await loadAutoUpdateKeys()
  }
  if (activeTab.value === 'results') {
    await loadResultList()
  }
})

async function ensureProfile() {
  if (!userStore.token) {
    return
  }
  if (!profile.userId || !profile.userName) {
    try {
      await userStore.getInfo()
    } catch (error) {
      errorMessage.value = error.message
    }
  }
}

async function loadMyKeys() {
  errorMessage.value = ''
  if (!myKeyQuery.userId) {
    await ensureProfile()
  }
  if (!myKeyQuery.userId) {
    myKeys.value = []
    myKeyTotal.value = 0
    return
  }

  myKeysLoading.value = true
  try {
    const response = await listLifecycleKeys(myKeyQuery)
    myKeys.value = response.rows || []
    myKeyTotal.value = response.total ?? myKeys.value.length
    selectedIds.value = []
  } catch (error) {
    errorMessage.value = error.message
    myKeys.value = []
    myKeyTotal.value = 0
  } finally {
    myKeysLoading.value = false
  }
}

async function loadAutoUpdateKeys() {
  errorMessage.value = ''
  if (!autoUpdateQuery.userId) {
    await ensureProfile()
  }
  if (!autoUpdateQuery.userId) {
    autoUpdateKeys.value = []
    autoUpdateTotal.value = 0
    return
  }

  autoUpdateLoading.value = true
  try {
    const response = await listLifecycleKeys(autoUpdateQuery)
    autoUpdateKeys.value = response.rows || []
    autoUpdateTotal.value = response.total ?? autoUpdateKeys.value.length
  } catch (error) {
    errorMessage.value = error.message
    autoUpdateKeys.value = []
    autoUpdateTotal.value = 0
  } finally {
    autoUpdateLoading.value = false
  }
}

/**
 * 打开「申请自动更新权限」弹窗（D2）。
 * 该入口由已删除的「权限管理」页迁移而来，原先还要选“生成域/状态域”两类，
 * 现只剩 AUTO_UPDATE 一项，因此不再需要选择，直接弹窗填理由。
 */
function openPermissionDialog() {
  if (canManageAutoUpdate.value) {
    proxy.$modal.msgInfo('当前账号已具备自动更新权限，无需申请')
    return
  }
  permissionReason.value = ''
  permissionError.value = ''
  permissionDialogOpen.value = true
}

async function submitPermission() {
  permissionError.value = ''
  if (!userStore.token) {
    permissionError.value = '登录状态已失效，请重新登录后再提交。'
    return
  }
  // 与后端 PermissionRequestServiceImpl 的校验保持一致（理由至少 4 字符），
  // 前端先拦一次，避免无意义的往返。
  const reason = permissionReason.value.trim()
  if (reason.length < 4) {
    permissionError.value = '申请理由至少 4 个字符。'
    return
  }
  if (!profile.userId) {
    await ensureProfile()
  }
  if (!profile.userId) {
    permissionError.value = '当前登录用户信息不完整，请刷新资料后重试。'
    return
  }

  permissionSubmitting.value = true
  try {
    // 阶段 8：权限申请接口已随审批流整体下线，这里不再调用。
    //
    // 新口径：密钥自动更新**不再需要申请** —— 准入由资源属主决定
    // （LifecycleKeyController 的 canAccess：属主或管理员）。
    // 如实告知"可以直接操作"，而不是伪造一次"已提交"：
    // 伪造成功提示比报错更糟，用户会去等一个永远不会来的审批。
    proxy.$modal.msgInfo('密钥自动更新已无需申请：你自己的密钥可直接在「密钥更新」中开启')
    permissionDialogOpen.value = false
    permissionReason.value = ''
    await loadAutoUpdatePermissionState()
  } catch (error) {
    permissionError.value = error.message
  } finally {
    permissionSubmitting.value = false
  }
}

async function loadAutoUpdatePermissionState() {
  // 阶段 8：不再查询"已批准的临时申请"—— 该概念已随审批流移除。
  approvedAutoUpdateRequestId.value = null
}

function handleSelectionChange(selection) {
  selectedIds.value = selection.map((item) => item.keyId)
}

function searchMyKeys() {
  myKeyQuery.pageNum = 1
  loadMyKeys()
}

function resetMyKeys() {
  myKeyQuery.pageNum = 1
  myKeyQuery.pageSize = 10
  myKeyQuery.keyName = ''
  myKeyQuery.encrytName = ''
  loadMyKeys()
}

function searchAutoUpdate() {
  autoUpdateQuery.pageNum = 1
  loadAutoUpdateKeys()
}

function resetAutoUpdate() {
  autoUpdateQuery.pageNum = 1
  autoUpdateQuery.pageSize = 10
  autoUpdateQuery.keyName = ''
  autoUpdateQuery.autoUpdate = ''
  loadAutoUpdateKeys()
}

function reloadCurrentTab() {
  if (activeTab.value === 'results') {
    loadResultList()
    return
  }
  if (activeTab.value === 'autoupdate') {
    loadAutoUpdateKeys()
    loadAutoUpdatePermissionState()
    return
  }
  loadMyKeys()
}

async function loadResultList() {
  errorMessage.value = ''
  resultLoading.value = true
  try {
    const response = await listLifecycleOperationRecords(resultQuery)
    resultList.value = response.rows || []
    resultTotal.value = response.total ?? resultList.value.length
  } catch (error) {
    errorMessage.value = error.message
    resultList.value = []
    resultTotal.value = 0
  } finally {
    resultLoading.value = false
  }
}

function searchResults() {
  resultQuery.pageNum = 1
  loadResultList()
}

function resetResults() {
  resultQuery.pageNum = 1
  resultQuery.pageSize = 10
  resultQuery.actionType = ''
  resultQuery.receiveStatus = ''
  loadResultList()
}

async function openUpdateDialog(row) {
  errorMessage.value = ''
  const keyId = row?.keyId || selectedIds.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning('请先选择一条密钥记录')
    return
  }

  try {
    const response = await getLifecycleKey(keyId)
    const record = response.data
    if (!record) {
      proxy.$modal.msgWarning('未找到对应密钥')
      return
    }
    if (isRevoked(record.status)) {
      proxy.$modal.msgWarning('已回收密钥不允许更新')
      return
    }

    updateForm.keyId = record.keyId
    updateForm.encrytType = record.encrytType || ''
    updateForm.encrytName = record.encrytName || ''
    updateForm.keyName = record.keyName || ''
    updateForm.keyUse = record.keyUse || ''
    updateForm.keyDomain = record.keyDomain || ''
    // 每次打开都从库里取当前版本，并清掉上一次遗留的轮换状态 ——
    // 否则"上一次勾了刷新材料、这次只想改名字"会意外触发轮换。
    updateForm.version = record.version ?? 1
    rotateRequested.value = false
    resetRotationMaterial()
    updateDialogOpen.value = true
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function submitUpdate() {
  if (!updateFormRef.value) {
    return
  }

  try {
    await updateFormRef.value.validate()
  } catch {
    return
  }

  updateSubmitting.value = true
  errorMessage.value = ''
  // 阶段 4（§5.3）：是否轮换由用户**显式选择**，不再靠"有没有带 uA"反推。
  // 那个旧判据在部分刷新下已经失效 —— §5.3 要求更新时 uA **保持不变**，
  // 也就是请求里带的正是与库中相同的那个值，从数据上看和"只改名字"没有区别。
  const rotating = rotateRequested.value
  if (rotating && !rotationAvailable.value) {
    errorMessage.value = rotationBlockReason.value
    updateSubmitting.value = false
    return
  }
  // 合成需要的那半私钥：拿不到就**不要提交**。
  // 先提交再合成会让库里出现一个版本 +1、而本机根本没有对应 d_A 的密钥 ——
  // 那正是本次要消灭的静默错配，不能换个地方再造一次。
  const localKeyFile = rotating ? keyring.get(updateForm.keyId) : null
  if (rotating && !localKeyFile) {
    errorMessage.value = `本机密钥环里没有密钥 ${updateForm.keyId} 的私钥文件，无法合成新版本。`
    updateSubmitting.value = false
    return
  }
  try {
    const response = await updateLifecycleKey({
      keyId: updateForm.keyId,
      keyName: normalizeText(updateForm.keyName),
      keyUse: normalizeText(updateForm.keyUse),
      keyDomain: normalizeText(updateForm.keyDomain),
      // 显式声明意图；ua 只作为一致性校验输入（服务端会要求它与库中一致）。
      rotate: rotating,
      ua: rotating ? rotationMaterial.publicKey : undefined
      // 刻意**不传** autoUpdate：这是"只改元数据"的更新。
      // 带上它（哪怕值与库里相同）曾让后端判定为"要改自动更新"并拒绝，
      // 报错却是"没有自动更新操作权限" —— 请求与报错对不上，很难查。
    })
    if (rotating) {
      const nextVersion = response?.data?.version ?? versionAfter.value
      // 服务端只做完了"KGC 那一半"。要真正拿到可用的新密钥，必须在本机
      // 用**不变的 u** 与新的部分密钥合成新的 d_A，并就地更新密钥环 ——
      // 否则本机留着的仍是旧版本的私钥，下次解密会失败，而界面上一切正常。
      await syncLocalKeyAfterRotation(response?.data, localKeyFile)
      proxy.$modal.msgSuccess(`密钥已部分刷新，版本更迭至 v${nextVersion}，正在上链存证`)
    } else {
      proxy.$modal.msgSuccess('密钥更新成功（仅元数据，版本不变）')
    }
    updateDialogOpen.value = false
    resetRotationMaterial()
    await loadMyKeys()
    if (activeTab.value === 'autoupdate') {
      await loadAutoUpdateKeys()
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    updateSubmitting.value = false
  }
}

/**
 * 轮换后在本机合成新版本的 `d_A` 并**就地替换**密钥环里的密钥文件。
 *
 * 为什么必须在这里做、且失败要显式报出来
 * --------------------------------------
 * 服务端已经落库了新版本（这个动作不可逆）。如果这一步静默失败，
 * 用户看到"更新成功"，而本机保存的还是**旧版本**的私钥 —— 下次解开新信封时
 * 只会得到一句含糊的"完整性校验失败"，没人能想到是轮换时没跟上。
 * 所以这里失败要单独报、要报得足够具体，让用户知道该重新导出哪一把。
 *
 * 密钥环损坏（同 key_id 私钥不同会抛错）不是异常情况而是**安全信号**：
 * 它意味着本机那份与链上这份对不上了，必须让人来判断，不能自动覆盖。
 */
async function syncLocalKeyAfterRotation(updatedRecord, previousKeyFile) {
  if (!updatedRecord?.keyValue) {
    throw new Error('轮换成功但服务端未返回新的部分密钥，无法在本机合成新版本，请重新导出该密钥文件')
  }
  let commonParams = null
  if (String(updatedRecord.encrytName || '').trim().toUpperCase() === 'SSCL') {
    // SSCL 的合成需要拉格朗日插值用的公共参数（xIndex / yIndex / PPub）
    commonParams = await getCommonParams({
      encrytType: updatedRecord.encrytType,
      encrytName: updatedRecord.encrytName
    })
  }
  const composed = composeUpdatedPrivateKey({
    algorithm: updatedRecord.encrytName,
    keyValue: updatedRecord.keyValue,
    clientPrivateHex: previousKeyFile.private_share,
    commonParams
  })
  const nextKeyFile = await buildKeyFile({
    keyId: updatedRecord.keyId,
    userId: previousKeyFile.user_id,
    algorithm: updatedRecord.encrytName,
    privateShare: composed.finalPrivateKey,
    publicKey: composed.finalPublicKey || ''
  })
  // importKeyFile 在同 key_id 私钥不同时会抛错。这里显然会不同（本来就是要换），
  // 所以先移除旧的再导入 —— 移除的是**已被服务端废弃的版本**，
  // 而它的替代品已经在手上（nextKeyFile 构造成功才会走到这里）。
  keyring.remove(updatedRecord.keyId)
  try {
    await keyring.importKeyFile(nextKeyFile)
  } catch (error) {
    // 导入失败就把旧文件放回去 —— 宁可留下一份已知过期的私钥（看得出问题），
    // 也不要留下一个空的密钥位（表现为"从来没导入过"，更难看懂）。
    try {
      await keyring.importKeyFile(previousKeyFile)
    } catch {
      // 回填也失败就不再掩盖：下面的报错会让用户重新导出
    }
    throw new Error(`本机密钥文件更新失败：${error.message}。请到「密钥生成」页重新导出该密钥文件`)
  }
  // 顺手把新版密钥文件下载一份：密钥环是本浏览器的，换台机器就没了，
  // 而这一版的私钥只存在于本机 —— 不下载就没有第二份。
  downloadText(serializeKeyFile(nextKeyFile), `kms-key-${updatedRecord.keyId}-v${updatedRecord.version}.json`)
}

/**
 * 触发浏览器下载一段文本。
 *
 * 与 `views/generate/create.vue` 里的同名函数一致 —— 那里已经有一份，
 * 但两边都不值得为这 8 行引一个模块依赖。真正的重复风险在**密码学**上
 * （已抽到 `utils/cl-key.js`），这里只是样板。
 */
function downloadText(text, filename) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function handleRevoke(row) {
  const ids = row?.keyId ? [row.keyId] : [...selectedIds.value]
  if (!ids.length) {
    proxy.$modal.msgWarning('请先选择需要回收的密钥')
    return
  }

  const revokedIds = ids.filter((keyId) => {
    const record = myKeys.value.find((item) => item.keyId === keyId)
    return record && isRevoked(record.status)
  })
  if (revokedIds.length) {
    proxy.$modal.msgWarning(`密钥 ${revokedIds.join(', ')} 已回收，无需重复操作`)
    return
  }

  proxy.$modal.confirm(`确认仅回收 KMS 侧引用/访问记录 ${ids.join(', ')}？该操作不等同于 Demo 侧能力销毁或节点级密钥删除。`).then(async () => {
    errorMessage.value = ''
    try {
      for (const keyId of ids) {
        await revokeLifecycleKey(keyId)
      }
      proxy.$modal.msgSuccess('KMS引用回收成功')
      await loadMyKeys()
      await loadAutoUpdateKeys()
      await loadResultList()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function toggleAutoUpdate(row) {
  if (isRevoked(row.status)) {
    ElMessage.warning('该密钥已回收，不可开启自动更新')
    return
  }

  const nextValue = isAutoUpdateEnabled(row.autoUpdate) ? '0' : '1'
  const actionText = nextValue === '1' ? '启用' : '禁用'
  proxy.$modal.confirm(`确认${actionText}密钥 "${row.keyName}" 的自动更新功能？`).then(async () => {
    errorMessage.value = ''
    try {
      await updateLifecycleAutoUpdate({ keyId: row.keyId, autoUpdate: nextValue })
      proxy.$modal.msgSuccess(`已${actionText}自动更新`)
      await loadAutoUpdateKeys()
      await loadMyKeys()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

async function showDetail(keyId) {
  errorMessage.value = ''
  try {
    const response = await getLifecycleKey(keyId)
    selectedKey.value = response.data || null
    detailDialogOpen.value = Boolean(selectedKey.value)
    // 版本更迭轨迹单独取一次：详情接口只返回"当前版本"，
    // 而"更迭过程"（v1 创建 → v2 轮换 → …）在操作记录表里。
    if (detailDialogOpen.value) {
      await loadVersionHistory(keyId)
    }
  } catch (error) {
    errorMessage.value = error.message
  }
}

function receiveResult(row) {
  proxy.$modal.confirm(`确认接收密钥 ${row.keyName || row.keyId} 的${actionTypeText(row.actionType)}结果？`).then(async () => {
    errorMessage.value = ''
    try {
      await receiveLifecycleOperationRecord(row.recordId)
      proxy.$modal.msgSuccess('结果已接收')
      await loadResultList()
      await loadMyKeys()
      await loadAutoUpdateKeys()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function handleRollback() {
  if (!approvedAutoUpdateRequestId.value) {
    proxy.$modal.msgWarning('没有可回退的临时权限')
    return
  }

  proxy.$modal.confirm('确认回退自动更新临时权限？').then(async () => {
    errorMessage.value = ''
    try {
      // 阶段 8：回退接口已随审批流下线。新模型下没有"临时权限"可回退 ——
      // 自动更新的准入是静态的（属主即可），不存在需要收回的临时状态。
      proxy.$modal.msgInfo('当前模型下不存在临时权限，无需回退')
      approvedAutoUpdateRequestId.value = null
      await loadAutoUpdatePermissionState()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function normalizeText(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : text
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 3 || status === 'Revoked' || status === 'REVOKED'
}

function autoUpdateText(value) {
  return isAutoUpdateEnabled(value) ? '已开启' : '已关闭'
}

function chainStatusText(status) {
  return { '0': '待上链', '1': '已上链', '2': '上链失败' }[String(status)] || '-'
}

function chainStatusType(status) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[String(status)] || 'info'
}

function actionTypeText(value) {
  return { UPDATE: '密钥更新', REVOKE: 'KMS引用回收' }[value] || '-'
}

function actionSourceText(value) {
  return { MANUAL: '手动', AUTO: '自动' }[value] || '-'
}

function resultStatusText(value) {
  return { '0': '处理中', '1': '成功', '2': '失败' }[String(value)] || '-'
}

function resultStatusType(value) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[String(value)] || 'info'
}

function receiveStatusText(row) {
  if (String(row?.resultStatus) === '0') {
    return '处理中'
  }
  return String(row?.receiveStatus) === '1' ? '已接收' : '待接收'
}

function receiveStatusType(row) {
  if (String(row?.resultStatus) === '0') {
    return 'info'
  }
  return String(row?.receiveStatus) === '1' ? 'success' : 'warning'
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

// 版本更迭轨迹里的操作时间：后端返回的是 ISO 串（2026-09-26T17:53:25.000+08:00），
// 直接渲染出来带 T 和毫秒，与页面其它时间（2026-09-26 17:53:24）不一致，
// 截图放进文档里很扎眼。这里统一成同样的 `YYYY-MM-DD HH:mm:ss`。
function formatActionTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function statusText(status) {
  const normalized = status == null ? '' : String(status)
  return {
    '0': '有效',
    '1': '已冻结',
    '2': '已更新',
    '3': '已回收',
    Valid: '有效',
    Active: '有效',
    ACTIVE: '有效',
    Frozen: '已冻结',
    FROZEN: '已冻结',
    Replaced: '已更新',
    Rotated: '已更新',
    ROTATED: '已更新',
    Revoked: '已回收',
    REVOKED: '已回收'
  }[normalized] || (status == null ? '-' : String(status))
}

function statusTagType(status) {
  const normalized = status == null ? '' : String(status)
  if (isRevoked(normalized)) {
    return 'danger'
  }
  if (['1', '2', 'Frozen', 'FROZEN', 'Replaced', 'Rotated', 'ROTATED'].includes(normalized)) {
    return 'warning'
  }
  if (['0', 'Valid', 'Active', 'ACTIVE'].includes(normalized)) {
    return 'success'
  }
  return 'info'
}

function roleText(level) {
  return roleLevelText(level)
}
</script>

<style scoped>
.lifecycle-page {
  animation: fade-in 0.5s ease;
}

/* 权限条：D2 把「申请自动更新权限」入口放在页内，替代原先跳转到权限管理页 */
.permission-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: var(--kms-surface-2);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius-md, 8px);
}

.permission-bar-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.permission-bar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.error-text {
  color: var(--kms-danger-strong);
  font-size: var(--kms-font-size-sm, 13px);
  margin: 0;
}

.lifecycle-page .mb12 {
  margin-bottom: 12px;
}

.header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.profile-grid,
.quick-actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.quick-actions {
  align-items: center;
  padding: 8px 0;
}

.query-form {
  margin-bottom: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px 24px;
}

/* 手动轮换区块：按钮 + 说明 + 新材料状态 */
.rotation-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.rotation-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #909399;
}

.rotation-ready {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 新材料明细：私钥默认打码，可显示/复制 */
.rotation-material {
  width: 100%;
}

.mat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mat-label {
  font-size: 12px;
  color: #606266;
}

.mat-value {
  flex: 1 1 220px;
  min-width: 0;
}

/* 版本更迭轨迹 */
.version-history {
  margin-top: 18px;
}

.version-history h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}

@media (max-width: 768px) {
  .profile-grid,
  .quick-actions {
    flex-direction: column;
    align-items: stretch;
  }
}

.lifecycle-dashboard {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  margin-top: 20px;
}
.inner-sidenav {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius);
  padding: 12px;
}
.inner-sidenav .nav-item {
  padding: 12px 16px;
  border-radius: var(--kms-radius-sm);
  cursor: pointer;
  color: var(--kms-text-secondary);
  transition: all var(--kms-transition);
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 500;
}
.inner-sidenav .nav-item:hover {
  background: var(--kms-surface-3);
  color: var(--kms-text-primary);
}
.inner-sidenav .nav-item.active {
  background: var(--kms-brand-subtle);
  color: var(--kms-brand-text);
  border: 1px solid var(--kms-brand-border);
}
.nav-link {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--kms-border);
  text-align: center;
}
.inner-main-content {
  flex-grow: 1;
  min-width: 0;
  position: relative;
}
.tab-pane {
  animation: fade-in 0.3s ease-out;
}
.floating-action-bar {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  background: var(--kms-surface-overlay);
  border: 1px solid var(--kms-border-strong);
  padding: 12px 24px;
  border-radius: var(--kms-radius-pill);
  display: flex;
  align-items: center;
  gap: 20px;
  box-shadow: var(--kms-shadow-md);
}
.selection-count {
  color: var(--kms-brand-text);
  font-weight: bold;
}
.fab-actions {
  display: flex;
  gap: 8px;
}
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}
.fade-slide-enter-from, .fade-slide-leave-to {
  opacity: 0;
  transform: translate(-50%, -20px);
}
@media (max-width: 960px) {
  .lifecycle-dashboard {
    flex-direction: column;
  }
  .inner-sidenav {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
  }
}

/* 表格右侧固定列背景：原实现为兼容暗色模式硬编码 #141923，
   浅色下会形成深色竖条。改为跟随表面层次令牌。 */
:deep(.el-table) .el-table-fixed-column--right,
:deep(.el-table) .el-table__fixed-right::before,
:deep(.el-table) .el-table__fixed::before {
  background-color: var(--kms-surface-1);
}

:deep(.el-table) th.el-table-fixed-column--right {
  background-color: var(--kms-surface-2);
}

:deep(.el-table--striped) .el-table__body tr.el-table__row--striped td.el-table-fixed-column--right {
  background-color: var(--kms-surface-2);
}

:deep(.el-table) .el-table__body tr:hover > td.el-table-fixed-column--right,
:deep(.el-table) .el-table__body tr.hover-row > td.el-table-fixed-column--right {
  background-color: var(--kms-brand-subtle);
}
</style>
