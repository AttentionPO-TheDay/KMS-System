<template>
  <div class="app-container">
    <div class="filter-container">
      <el-card class="box-card">
        <template #header>
          <div class="card-header">
            <div class="header-left">
              <span>🌐 节点管理</span>
              <el-tag v-if="currentBlockchainConfig" type="info" size="small" class="ml-2">
                当前区块链: {{ currentBlockchainConfig }}
              </el-tag>
              <el-tag v-else type="danger" size="small" class="ml-2">
                ⚠️ 未配置区块链
              </el-tag>
            </div>
            <el-button
              type="primary"
              icon="Plus"
              @click="showAddDialog"
              :disabled="!currentBlockchainConfig || currentBlockchainConfig === '未配置' || currentBlockchainConfig === '获取失败'"
            >
              注册新节点
            </el-button>
          </div>
        </template>
        
        <!-- 搜索过滤 -->
        <el-row :gutter="20">
          <el-col :span="6">
            <el-input
              v-model="searchForm.node_id"
              placeholder="节点ID"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            />
          </el-col>
          <el-col :span="6">
            <el-input
              v-model="searchForm.name"
              placeholder="节点名称"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            />
          </el-col>
          <el-col :span="6">
            <el-select v-model="searchForm.status" placeholder="状态" clearable @change="handleSearch">
              <el-option label="已注册" value="registered" />
              <el-option label="活跃" value="active" />
              <el-option label="Kyber已上传" value="kyber_uploaded" />
              <el-option label="Falcon已上传" value="falcon_uploaded" />
              <el-option label="非活跃" value="inactive" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-button type="primary" icon="Search" @click="handleSearch">搜索</el-button>
            <el-button icon="Refresh" @click="resetSearch">重置</el-button>
          </el-col>
        </el-row>
      </el-card>
    </div>

    <!-- 节点列表 -->
    <el-card class="box-card" style="margin-top: 20px;">
      <!-- 批量操作工具栏 -->
      <div v-if="selectedNodes.length > 0" style="margin-bottom: 15px; padding: 10px; background-color: #f0f9ff; border-left: 4px solid #409eff; border-radius: 4px;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <span style="color: #606266;">
            已选择 <strong style="color: #409eff;">{{ selectedNodes.length }}</strong> 个节点
          </span>
          <div style="display: flex; gap: 10px;">
            <el-button type="danger" size="small" @click="batchDeleteNodes" :loading="batchDeleting">
              <template #icon><Delete /></template>
              批量删除
            </el-button>
            <el-button type="default" size="small" @click="clearSelection">
              取消选择
            </el-button>
          </div>
        </div>
      </div>

      <el-table
        :data="nodeList"
        style="width: 100%"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        ref="tableRef"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="node_id" label="节点ID" width="120" />
        <el-table-column prop="name" label="节点名称" width="150" />
        <el-table-column prop="ip_address" label="IP地址" width="120" />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column label="状态" width="120">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Kyber密钥" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.kyber_key_ready" type="success" size="small">
              已生成
            </el-tag>
            <el-tag v-else type="warning" size="small">
              未生成
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Falcon密钥" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.falcon_key_ready" type="success" size="small">
              已生成
            </el-tag>
            <el-tag v-else type="warning" size="small">
              未生成
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_active" label="最后活跃" width="180" />
        <el-table-column label="操作" width="900" :resizable="false">
          <template #default="scope">
            <div style="display: inline-flex; gap: 8px; flex-wrap: nowrap; white-space: nowrap; overflow-x: auto;">
              <el-button type="info" size="small" @click="viewNodeDetails(scope.row)" style="flex-shrink: 0;">
                查看详情
              </el-button>
              <el-button type="primary" size="small" @click="showEditDialog(scope.row)" style="flex-shrink: 0;">
                编辑节点
              </el-button>
              <el-button type="success" size="small" @click="testSessionKey(scope.row)" style="flex-shrink: 0;">
                测试会话密钥
              </el-button>
              <el-button
                v-if="!scope.row.falcon_key_ready"
                type="warning"
                size="small"
                @click="generateFalconKeys(scope.row)"
                :loading="scope.row.generatingFalcon"
                style="flex-shrink: 0;"
              >
                生成Falcon密钥
              </el-button>
              <el-button type="warning" size="small" @click="showUpdateKeysDialog(scope.row)" style="flex-shrink: 0;">
                更新密钥
              </el-button>
              <el-button
                type="danger"
                size="small"
                @click="deleteNode(scope.row)"
                :loading="scope.row.deleting"
                style="flex-shrink: 0;"
              >
                删除节点
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.size"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
        style="margin-top: 20px; text-align: right;"
      />
    </el-card>

    <!-- 添加节点对话框 -->
    <el-dialog v-model="addDialogVisible" title="注册新节点" width="800px">
      <el-form :model="addForm" :rules="addRules" ref="addFormRef" label-width="120px">
        <!-- 基本信息 -->
        <el-divider content-position="left">基本信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="节点ID" prop="node_id">
              <el-input v-model="addForm.node_id" placeholder="请输入节点ID" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="节点名称" prop="name">
              <el-input v-model="addForm.name" placeholder="请输入节点名称" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="IP地址" prop="ip_address">
              <el-input v-model="addForm.ip_address" placeholder="请输入IP地址" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="端口" prop="port">
              <el-input-number v-model="addForm.port" :min="1" :max="65535" placeholder="请输入端口" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 联系信息 -->
        <el-divider content-position="left">联系信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="联系人" prop="contact_person">
              <el-input v-model="addForm.contact_person" placeholder="请输入联系人姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="addForm.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="addForm.email" placeholder="请输入邮箱地址" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 组织信息 -->
        <el-divider content-position="left">组织信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属组织" prop="organization">
              <el-input v-model="addForm.organization" placeholder="请输入所属组织" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="部门" prop="department">
              <el-input v-model="addForm.department" placeholder="请输入部门" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="物理位置" prop="location">
              <el-input v-model="addForm.location" placeholder="请输入节点物理位置" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 技术信息 -->
        <el-divider content-position="left">技术信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="节点类型" prop="node_type">
              <el-select v-model="addForm.node_type" placeholder="请选择节点类型" style="width: 100%">
                <el-option label="全节点" value="full" />
                <el-option label="轻节点" value="light" />
                <el-option label="验证节点" value="validator" />
                <el-option label="存储节点" value="storage" />
                <el-option label="计算节点" value="compute" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标签" prop="tags">
              <el-input v-model="addForm.tags" placeholder="请输入标签，用逗号分隔" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 密钥配置 -->
        <el-divider content-position="left">
          <el-icon><Key /></el-icon>
          <span style="margin-left: 8px">后量子密码学配置</span>
        </el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Kyber安全级别" prop="kyber_security_level">
              <el-select v-model="addForm.kyber_security_level" placeholder="请选择Kyber安全级别" style="width: 100%">
                <el-option label="Kyber-512 (推荐)" value="512">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                      <el-tag size="small" type="success">推荐</el-tag>
                      <span style="margin-left: 8px">Kyber-512</span>
                    </span>
                    <span style="color: #8492a6; font-size: 12px">无证书方案</span>
                  </div>
                </el-option>
                <el-option label="Kyber-768 (高安全)" value="768">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                      <el-tag size="small" type="warning">高安全</el-tag>
                      <span style="margin-left: 8px">Kyber-768</span>
                    </span>
                    <span style="color: #8492a6; font-size: 12px">无证书方案</span>
                  </div>
                </el-option>
                <el-option label="Kyber-1024 (最高安全)" value="1024">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                      <el-tag size="small" type="danger">最高安全</el-tag>
                      <span style="margin-left: 8px">Kyber-1024</span>
                    </span>
                    <span style="color: #8492a6; font-size: 12px">无证书方案</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Falcon安全级别" prop="falcon_security_level">
              <el-select v-model="addForm.falcon_security_level" placeholder="请选择Falcon安全级别" style="width: 100%">
                <el-option label="Falcon-512 (推荐)" value="512">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                      <el-tag size="small" type="success">推荐</el-tag>
                      <span style="margin-left: 8px">Falcon-512</span>
                    </span>
                    <span style="color: #8492a6; font-size: 12px">基于陷门</span>
                  </div>
                </el-option>
                <el-option label="Falcon-1024 (最高安全)" value="1024">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                      <el-tag size="small" type="danger">最高安全</el-tag>
                      <span style="margin-left: 8px">Falcon-1024</span>
                    </span>
                    <span style="color: #8492a6; font-size: 12px">基于陷门</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="硬件规格" prop="hardware_spec">
              <el-input
                v-model="addForm.hardware_spec"
                type="textarea"
                :rows="2"
                placeholder="请输入硬件配置信息，如：CPU: Intel i7, RAM: 16GB, Storage: 1TB SSD"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="节点描述" prop="description">
              <el-input
                v-model="addForm.description"
                type="textarea"
                :rows="3"
                placeholder="请输入节点详细描述信息"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="addDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleAddNode" :loading="addLoading">
            注册节点
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 编辑节点对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑节点信息" width="800px">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="120px">
        <!-- 基本信息 - 只读显示 -->
        <el-divider content-position="left">基本信息（不可修改）</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="节点ID">
              <el-input v-model="editForm.node_id" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="节点名称">
              <el-input v-model="editForm.name" disabled />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="IP地址">
              <el-input v-model="editForm.ip_address" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="端口号">
              <el-input v-model="editForm.port" disabled />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 联系信息 - 可修改 -->
        <el-divider content-position="left">联系信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="手机号" prop="phone">
              <el-input v-model="editForm.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="editForm.email" placeholder="请输入邮箱" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="联系人" prop="contact_person">
              <el-input v-model="editForm.contact_person" placeholder="请输入联系人" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 组织信息 - 可修改 -->
        <el-divider content-position="left">组织信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属组织" prop="organization">
              <el-input v-model="editForm.organization" placeholder="请输入所属组织" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="部门" prop="department">
              <el-input v-model="editForm.department" placeholder="请输入部门" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="物理位置" prop="location">
              <el-input v-model="editForm.location" placeholder="请输入物理位置" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 技术信息 - 可修改 -->
        <el-divider content-position="left">技术信息</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="节点类型" prop="node_type">
              <el-select v-model="editForm.node_type" placeholder="请选择节点类型">
                <el-option label="全节点" value="full" />
                <el-option label="轻节点" value="light" />
                <el-option label="验证节点" value="validator" />
                <el-option label="存储节点" value="storage" />
                <el-option label="计算节点" value="compute" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Kyber安全级别" prop="kyber_security_level">
              <el-select v-model="editForm.kyber_security_level" placeholder="请选择Kyber安全级别">
                <el-option label="Kyber-512" value="512" />
                <el-option label="Kyber-768" value="768" />
                <el-option label="Kyber-1024" value="1024" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Falcon安全级别" prop="falcon_security_level">
              <el-select v-model="editForm.falcon_security_level" placeholder="请选择Falcon安全级别">
                <el-option label="Falcon-512" value="512" />
                <el-option label="Falcon-1024" value="1024" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="硬件规格" prop="hardware_spec">
              <el-input
                v-model="editForm.hardware_spec"
                type="textarea"
                :rows="3"
                placeholder="请输入硬件规格信息"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="节点描述" prop="description">
              <el-input
                v-model="editForm.description"
                type="textarea"
                :rows="3"
                placeholder="请输入节点描述"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="24">
            <el-form-item label="标签" prop="tags">
              <el-input v-model="editForm.tags" placeholder="请输入标签，用逗号分隔" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleEditNode" :loading="editLoading">
            保存修改
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 节点详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="节点详情" width="1000px">
      <div v-if="selectedNode">
        <!-- 基本信息 -->
        <el-divider content-position="left">基本信息</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="节点ID">{{ selectedNode.node_id }}</el-descriptions-item>
          <el-descriptions-item label="节点名称">{{ selectedNode.name }}</el-descriptions-item>
          <el-descriptions-item label="IP地址">{{ selectedNode.ip_address }}</el-descriptions-item>
          <el-descriptions-item label="端口">{{ selectedNode.port }}</el-descriptions-item>
          <el-descriptions-item label="节点类型">
            <el-tag>{{ getNodeTypeText(selectedNode.node_type) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(selectedNode.status)">
              {{ getStatusText(selectedNode.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="最后活跃">{{ selectedNode.last_active }}</el-descriptions-item>
          <el-descriptions-item label="注册时间">{{ selectedNode.create_datetime }}</el-descriptions-item>
        </el-descriptions>

        <!-- 联系信息 -->
        <el-divider content-position="left">联系信息</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="联系人">{{ selectedNode.contact_person || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="手机号">{{ selectedNode.phone || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="邮箱" :span="2">{{ selectedNode.email || '未填写' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 组织信息 -->
        <el-divider content-position="left">组织信息</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="所属组织">{{ selectedNode.organization || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ selectedNode.department || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="物理位置" :span="2">{{ selectedNode.location || '未填写' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 技术信息 -->
        <el-divider content-position="left">技术信息</el-divider>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="硬件规格">
            <div style="white-space: pre-wrap;">{{ selectedNode.hardware_spec || '未填写' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="节点描述">
            <div style="white-space: pre-wrap;">{{ selectedNode.description || '未填写' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="标签">
            <div v-if="selectedNode.tags">
              <el-tag
                v-for="tag in selectedNode.tags.split(',')"
                :key="tag"
                style="margin-right: 8px; margin-bottom: 4px;"
                size="small"
              >
                {{ tag.trim() }}
              </el-tag>
            </div>
            <span v-else>未填写</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 密钥信息 -->
        <el-divider content-position="left">密钥信息</el-divider>

        <div v-loading="keyDetailsLoading">
          <!-- Kyber密钥信息 -->
          <el-card shadow="never" style="margin-bottom: 16px;">
            <template #header>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-weight: bold;">🔐 Kyber密钥对（安全级别: Kyber-{{ nodeKeyDetails?.kyber?.security_level || '512' }}）</span>
                <el-tag v-if="nodeKeyDetails?.kyber?.public_key" type="success" size="small">已生成</el-tag>
                <el-tag v-else type="info" size="small">未生成</el-tag>
              </div>
            </template>

            <el-descriptions :column="1" border>
              <el-descriptions-item label="Kyber公钥">
                <div v-if="nodeKeyDetails?.kyber?.public_key" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.kyber.public_key"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.kyber.public_key, 'Kyber公钥')"
                  >
                    复制
                  </el-button>
                </div>
                <el-tag v-else type="warning">未生成</el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="Kyber私钥">
                <div v-if="nodeKeyDetails?.kyber?.private_key" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.kyber.private_key"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.kyber.private_key, 'Kyber私钥')"
                  >
                    复制
                  </el-button>
                </div>
                <el-tag v-else type="warning">未生成</el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="Kyber部分私钥（KGC生成）">
                <div v-if="nodeKeyDetails?.kyber?.partial_key?.has_data" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.kyber.partial_key.encrypted_data"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.kyber.partial_key.encrypted_data, 'Kyber部分私钥')"
                  >
                    复制
                  </el-button>
                </div>
                <div v-else>
                  <el-tag type="info">{{ nodeKeyDetails?.kyber?.partial_key?.note || '暂无数据' }}</el-tag>
                </div>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- Falcon密钥信息 -->
          <el-card shadow="never" style="margin-bottom: 16px;">
            <template #header>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-weight: bold;">🦅 Falcon密钥对（安全级别: Falcon-{{ nodeKeyDetails?.falcon?.security_level || '512' }}）</span>
                <el-tag v-if="nodeKeyDetails?.falcon?.public_key" type="success" size="small">已生成</el-tag>
                <el-tag v-else type="info" size="small">未生成</el-tag>
              </div>
            </template>

            <el-descriptions :column="1" border>
              <el-descriptions-item label="Falcon公钥">
                <div v-if="nodeKeyDetails?.falcon?.public_key" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.falcon.public_key"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.falcon.public_key, 'Falcon公钥')"
                  >
                    复制
                  </el-button>
                </div>
                <el-tag v-else type="warning">未生成</el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="Falcon私钥">
                <div v-if="nodeKeyDetails?.falcon?.private_key" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.falcon.private_key"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.falcon.private_key, 'Falcon私钥')"
                  >
                    复制
                  </el-button>
                </div>
                <el-tag v-else type="warning">未生成</el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="Falcon部分私钥（KGC生成）">
                <div v-if="nodeKeyDetails?.falcon?.partial_key?.has_data" style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model="nodeKeyDetails.falcon.partial_key.encrypted_data"
                    type="textarea"
                    :rows="3"
                    readonly
                    style="flex: 1; font-family: monospace; font-size: 12px;"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    icon="CopyDocument"
                    @click="copyToClipboard(nodeKeyDetails.falcon.partial_key.encrypted_data, 'Falcon部分私钥')"
                  >
                    复制
                  </el-button>
                </div>
                <div v-else>
                  <el-tag type="info">{{ nodeKeyDetails?.falcon?.partial_key?.note || '暂无数据' }}</el-tag>
                  <div v-if="!nodeKeyDetails?.falcon?.partial_key?.has_data" style="margin-top: 8px; font-size: 12px; color: #909399;">
                    <i class="el-icon-info"></i> 部分私钥已在密钥生成过程中整合到Falcon私钥中
                  </div>
                </div>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 部分私钥接收状态 -->
          <el-card shadow="never">
            <template #header>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-weight: bold;">🔑 部分私钥接收状态</span>
                <el-tag v-if="nodeKeyDetails?.partial_key_received" type="success" size="small">已接收</el-tag>
                <el-tag v-else type="warning" size="small">未接收</el-tag>
              </div>
            </template>

            <el-descriptions :column="1" border>
              <el-descriptions-item label="总体状态">
                <el-tag v-if="nodeKeyDetails?.partial_key_received" type="success">
                  ✓ 已接收部分私钥
                </el-tag>
                <el-tag v-else type="warning">
                  ✗ 未接收部分私钥
                </el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="节点状态">
                <el-tag :type="getStatusType(nodeKeyDetails?.status)">
                  {{ getStatusText(nodeKeyDetails?.status) }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>
      </div>
    </el-dialog>

    <!-- 会话密钥测试对话框 -->
    <el-dialog v-model="sessionDialogVisible" title="会话密钥测试" width="600px">
      <el-form :model="sessionForm" label-width="120px">
        <el-form-item label="发起节点">
          <el-text>{{ sessionForm.from_node?.name }} ({{ sessionForm.from_node?.node_id }})</el-text>
        </el-form-item>
        <el-form-item label="目标节点">
          <el-select v-model="sessionForm.to_node_id" placeholder="选择目标节点" style="width: 100%">
            <el-option
              v-for="node in availableNodes"
              :key="node.node_id"
              :label="`${node.name} (${node.node_id})`"
              :value="node.node_id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="sessionDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="initiateSessionKey" :loading="sessionLoading">
            发起会话密钥分发
          </el-button>
        </span>
      </template>
    </el-dialog>

    

    <!-- 更新密钥对话框 -->
    <el-dialog
      v-model="updateKeysDialogVisible"
      title="更新节点密钥"
      width="600px"
      :close-on-click-modal="false"
    >
      <div style="padding: 20px 0;">
        <p style="margin-bottom: 20px; color: #606266;">
          为节点 <strong>{{ currentUpdateNode?.name }}</strong> ({{ currentUpdateNode?.node_id }}) 更新密钥：
        </p>

        <el-form :model="updateKeysForm" :rules="updateKeysRules" ref="updateKeysFormRef" label-width="120px">
          <el-form-item label="更新类型" prop="key_type">
            <el-radio-group v-model="updateKeysForm.key_type">
              <el-radio value="kyber">仅更新无证书Kyber密钥</el-radio>
              <el-radio value="falcon">仅更新无证书Falcon密钥</el-radio>
              <el-radio value="both">同时更新两种密钥</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item
            v-if="updateKeysForm.key_type === 'kyber' || updateKeysForm.key_type === 'both'"
            label="Kyber安全级别"
            prop="kyber_security_level"
          >
            <el-select v-model="updateKeysForm.kyber_security_level" placeholder="选择安全级别">
              <el-option label="Kyber-512 (推荐)" :value="512" />
              <el-option label="Kyber-768" :value="768" />
              <el-option label="Kyber-1024 (最高安全)" :value="1024" />
            </el-select>
            <div style="font-size: 12px; color: #909399; margin-top: 4px;">
              安全级别越高，密钥长度越长，安全性越强
            </div>
          </el-form-item>

          <el-form-item
            v-if="updateKeysForm.key_type === 'falcon' || updateKeysForm.key_type === 'both'"
            label="Falcon安全级别"
            prop="falcon_security_level"
          >
            <el-select v-model="updateKeysForm.falcon_security_level" placeholder="选择安全级别">
              <el-option label="Falcon-512 (推荐)" :value="512" />
              <el-option label="Falcon-1024 (最高安全)" :value="1024" />
            </el-select>
            <div style="font-size: 12px; color: #909399; margin-top: 4px;">
              Falcon只支持512和1024安全级别，安全级别越高，签名长度越长，安全性越强
            </div>
          </el-form-item>
        </el-form>

      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="updateKeysDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            @click="confirmUpdateKeys"
            :loading="updateKeysLoading"
          >
            确认更新
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { nodesApi } from '@/api/pqkds/nodes'
import { sessionKeysApi } from '@/api/pqkds/sessionKeys'
import { blockchainApi } from '@/api/pqkds/blockchain'

// 响应式数据
const loading = ref(false)
const nodeList = ref([])
const currentBlockchainConfig = ref('')
const currentBlockchainId = ref(null)

// 批量删除相关
const selectedNodes = ref([])
const batchDeleting = ref(false)
const tableRef = ref()

// 表单引用
const addFormRef = ref()
const editFormRef = ref()
const searchForm = reactive({
  node_id: '',
  name: '',
  status: ''
})

const pagination = reactive({
  page: 1,
  size: 10,
  total: 0
})

// 添加节点相关
const addDialogVisible = ref(false)
const addLoading = ref(false)
const addForm = reactive({
  node_id: '',
  name: '',
  ip_address: '',
  port: 8080,
  // 联系信息
  contact_person: '',
  phone: '',
  email: '',
  // 组织信息
  organization: '',
  department: '',
  location: '',
  // 技术信息
  node_type: 'full',
  hardware_spec: '',
  description: '',
  tags: '',
  // 密钥配置
  kyber_security_level: '512',  // 默认Kyber-512
  falcon_security_level: '512'  // 默认Falcon-512
})

const addRules = {
  node_id: [{ required: true, message: '请输入节点ID', trigger: 'blur' }],
  name: [{ required: true, message: '请输入节点名称', trigger: 'blur' }],
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    { pattern: /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/, message: '请输入正确的IP地址格式', trigger: 'blur' }
  ],
  port: [
    { required: true, message: '请输入端口', trigger: 'blur' },
    { type: 'number', min: 1, max: 65535, message: '端口范围应在1-65535之间', trigger: 'blur' }
  ],
  phone: [
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号格式', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  kyber_security_level: [{ required: true, message: '请选择Kyber安全级别', trigger: 'change' }],
  falcon_security_level: [{ required: true, message: '请选择Falcon安全级别', trigger: 'change' }]
}

// 编辑节点相关
const editDialogVisible = ref(false)
const editLoading = ref(false)
const editForm = reactive({
  id: null,
  node_id: '',
  name: '',
  ip_address: '',
  port: null,
  // 联系信息 - 可修改
  contact_person: '',
  phone: '',
  email: '',
  // 组织信息 - 可修改
  organization: '',
  department: '',
  location: '',
  // 技术信息 - 可修改
  node_type: 'full',
  hardware_spec: '',
  description: '',
  tags: '',
  // 密钥配置 - 可修改
  kyber_security_level: '512',
  falcon_security_level: '512'
})

const editRules = {
  phone: [
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号格式', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  kyber_security_level: [{ required: true, message: '请选择Kyber安全级别', trigger: 'change' }],
  falcon_security_level: [{ required: true, message: '请选择Falcon安全级别', trigger: 'change' }]
}

// 节点详情相关
const detailDialogVisible = ref(false)
const selectedNode = ref(null)
const nodeKeyDetails = ref(null)
const keyDetailsLoading = ref(false)

// 会话密钥测试相关
const sessionDialogVisible = ref(false)
const sessionLoading = ref(false)
const sessionForm = reactive({
  from_node: null,
  to_node_id: ''
})

// 计算属性
const availableNodes = computed(() => {
  return nodeList.value.filter(node =>
    node.node_id !== sessionForm.from_node?.node_id &&
    // 列表接口（NodeListSerializer）只回就绪布尔值，不带公钥本身 ——
    // falcon_public_key 实测 7.8MB/节点，列表带上它会撑爆响应。
    node.falcon_key_ready
  )
})

// 方法
const getCurrentBlockchainConfig = async (silent = false) => {
  try {
    const response = await blockchainApi.getActiveConfig()
    if (response.code === 2000 && response.data) {
      currentBlockchainConfig.value = response.data.name || '默认配置'
      currentBlockchainId.value = response.data.id
      if (!silent) ElMessage.success(`当前连接区块链: ${response.data.name}`)
    } else {
      currentBlockchainConfig.value = '未配置'
      currentBlockchainId.value = null
      if (!silent) ElMessage.warning('没有活跃的区块链配置，请先配置区块链网络')
    }
  } catch (error) {
    console.error('获取区块链配置失败:', error)
    currentBlockchainConfig.value = '获取失败'
    currentBlockchainId.value = null
  }
}

const getNodeList = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      limit: pagination.size,  // 后端期望的参数名是limit而不是size
      // 移除show_all参数，使用新的区块链配置过滤逻辑
      _t: Date.now(), // 添加时间戳防止缓存
      ...searchForm
    }
    const response = await nodesApi.getList(params)

    // 调试日志
    console.log('🔍 节点API响应:', response)
    console.log('📊 响应数据类型:', typeof response.data)
    console.log('📋 响应消息:', response.msg)

    if (response.code === 2000) {
      // 适配后端分页格式
      if (response.data && Array.isArray(response.data)) {
        // 直接返回数组的情况（新格式）
        nodeList.value = response.data
        pagination.total = response.total || response.data.length
        console.log(`✅ 使用新格式: ${response.data.length} 个节点`)
      } else if (response.data && response.data.results) {
        // 包含results的情况（DRF格式）
        nodeList.value = response.data.results
        pagination.total = response.data.count || 0
        console.log(`✅ 使用DRF格式: ${response.data.results.length} 个节点`)
      } else {
        nodeList.value = []
        pagination.total = 0
        console.log('⚠️ 未知响应格式，设为空列表')
      }

      // 显示当前区块链配置信息
      if (response.msg && response.msg.includes('当前区块链:')) {
        ElMessage.success(response.msg)
      }
    } else {
      console.error('❌ API响应错误:', response)
      ElMessage.error(response.msg || '获取节点列表失败')
    }
  } catch (error) {
    ElMessage.error('获取节点列表失败')
    console.error('Error fetching nodes:', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  getNodeList()
}

const resetSearch = () => {
  Object.assign(searchForm, {
    node_id: '',
    name: '',
    status: ''
  })
  handleSearch()
}

const handleSizeChange = (size) => {
  pagination.size = size
  getNodeList()
}

const handleCurrentChange = (page) => {
  pagination.page = page
  getNodeList()
}

const showAddDialog = () => {
  // 检查是否有活跃的区块链配置
  if (!currentBlockchainConfig.value || currentBlockchainConfig.value === '未配置' || currentBlockchainConfig.value === '获取失败') {
    ElMessage.error('❌ 没有活跃的区块链配置，无法注册节点。请先进入"区块链管理"菜单进行配置。')
    return
  }

  Object.assign(addForm, {
    node_id: '',
    name: '',
    ip_address: '',
    port: 8080,
    // 联系信息
    contact_person: '',
    phone: '',
    email: '',
    // 组织信息
    organization: '',
    department: '',
    location: '',
    // 技术信息
    node_type: 'full',
    hardware_spec: '',
    description: '',
    tags: '',
    // 密钥配置
    kyber_security_level: '512',
    falcon_security_level: '512'
  })
  addDialogVisible.value = true
}

const handleAddNode = async () => {
  addLoading.value = true
  try {
    const response = await nodesApi.register(addForm)
    if (response.code === 2000) {
      // 检查是否是重复注册
      if (response.data?.is_duplicate) {
        // 显示已注册节点的信息对话框
        ElMessageBox.alert(
          `节点ID: ${response.data.node_id}\n` +
          `节点名称: ${response.data.name}\n` +
          `IP地址: ${response.data.ip_address}:${response.data.port}\n` +
          `节点状态: ${getStatusText(response.data.status)}\n` +
          `注册时间: ${formatDateTime(response.data.create_datetime)}`,
          '节点已注册',
          {
            confirmButtonText: '关闭',
            type: 'info',
            customClass: 'duplicate-node-dialog',
            callback: () => {
              addDialogVisible.value = false
              getNodeList()
            }
          }
        )
      } else {
        // 新节点注册成功
        const timingInfo = response.data?.timing_info || {}
        const kyberTime = timingInfo.kyber_generation_time || 0
        const falconTime = timingInfo.falcon_generation_time || 0
        const totalTime = timingInfo.total_time || 0
        const kyberGenTime = response.data?.kyber_keygen_time
        const falconGenTime = response.data?.falcon_keygen_time

        let successMsg = `节点注册成功！`
        if (kyberGenTime) {
          successMsg += `\\n⏰ Kyber密钥生成时间: ${formatDateTime(kyberGenTime)}`
        }
        if (falconGenTime) {
          successMsg += `\\n⏰ Falcon密钥生成时间: ${formatDateTime(falconGenTime)}`
        }
        if (totalTime > 0) {
          successMsg += `\n⏱️ 总耗时: ${totalTime.toFixed(3)}秒`
        }
        if (kyberTime > 0) {
          successMsg += `\n🔑 Kyber密钥生成: ${kyberTime.toFixed(3)}秒`
        }
        if (falconTime > 0) {
          successMsg += `\n🔑 Falcon密钥生成: ${falconTime.toFixed(3)}秒`
        }

        ElMessage({
          message: successMsg,
          type: 'success',
          duration: 5000,
          dangerouslyUseHTMLString: false
        })

        addDialogVisible.value = false
        getNodeList()
      }
    } else {
      ElMessage.error(response.msg || '节点注册失败')
    }
  } catch (error) {
    ElMessage.error('节点注册失败')
    console.error('Error registering node:', error)
  } finally {
    addLoading.value = false
  }
}

// 显示编辑对话框
const showEditDialog = (node) => {
  Object.assign(editForm, {
    id: node.id,
    node_id: node.node_id,
    name: node.name,
    ip_address: node.ip_address,
    port: node.port,
    // 联系信息 - 可修改
    contact_person: node.contact_person || '',
    phone: node.phone || '',
    email: node.email || '',
    // 组织信息 - 可修改
    organization: node.organization || '',
    department: node.department || '',
    location: node.location || '',
    // 技术信息 - 可修改
    node_type: node.node_type || 'full',
    hardware_spec: node.hardware_spec || '',
    description: node.description || '',
    tags: node.tags || '',
    // 密钥配置 - 可修改
    kyber_security_level: node.kyber_security_level || '512',
    falcon_security_level: node.falcon_security_level || '512'
  })
  editDialogVisible.value = true
}

// 处理编辑节点
const handleEditNode = async () => {
  try {
    await editFormRef.value.validate()
    editLoading.value = true

    // 只提交可修改的字段
    const updateData = {
      // 联系信息
      contact_person: editForm.contact_person,
      phone: editForm.phone,
      email: editForm.email,
      // 组织信息
      organization: editForm.organization,
      department: editForm.department,
      location: editForm.location,
      // 技术信息
      node_type: editForm.node_type,
      hardware_spec: editForm.hardware_spec,
      description: editForm.description,
      tags: editForm.tags,
      // 密钥配置
      kyber_security_level: editForm.kyber_security_level,
      falcon_security_level: editForm.falcon_security_level
    }

    const response = await nodesApi.update(editForm.id, updateData)
    if (response.code === 2000) {
      ElMessage.success('节点信息更新成功')
      editDialogVisible.value = false
      getNodeList()
    } else {
      ElMessage.error(response.msg || '节点信息更新失败')
    }
  } catch (error) {
    if (error !== false) { // 不是表单验证失败
      ElMessage.error('节点信息更新失败')
      console.error('Error updating node:', error)
    }
  } finally {
    editLoading.value = false
  }
}

// 更新密钥相关
const updateKeysDialogVisible = ref(false)
const updateKeysLoading = ref(false)
const currentUpdateNode = ref(null)
const updateKeysForm = reactive({
  key_type: 'kyber',
  kyber_security_level: 512,
  falcon_security_level: 512,
  falcon_version: 'v2'  // 默认使用V2方案
})

const updateKeysRules = {
  key_type: [{ required: true, message: '请选择更新类型', trigger: 'change' }],
  kyber_security_level: [{ required: true, message: '请选择Kyber安全级别', trigger: 'change' }],
  falcon_security_level: [{ required: true, message: '请选择Falcon安全级别', trigger: 'change' }],
  falcon_version: [{ required: true, message: '请选择Falcon方案版本', trigger: 'change' }]
}

const viewNodeDetails = (node) => {
  selectedNode.value = node
  nodeKeyDetails.value = null
  detailDialogVisible.value = true
  // 延迟一下确保对话框打开后再加载数据
  setTimeout(() => {
    loadNodeKeyDetails()
  }, 100)
}

// 加载节点密钥详情
const loadNodeKeyDetails = async () => {
  if (!selectedNode.value) return

  keyDetailsLoading.value = true
  nodeKeyDetails.value = null

  try {
    const response = await nodesApi.getKeyDetails(selectedNode.value.node_id)

    if (response.code === 2000 && response.data) {
      nodeKeyDetails.value = response.data
      console.log('密钥详情加载成功:', response.data)
    } else {
      ElMessage.error(response.msg || '获取密钥详情失败')
      console.error('API返回错误:', response)
    }
  } catch (error) {
    console.error('获取密钥详情失败:', error)
    ElMessage.error('获取密钥详情失败: ' + (error.message || '网络错误'))
  } finally {
    keyDetailsLoading.value = false
  }
}

// 复制到剪贴板
const copyToClipboard = async (text, label) => {
  if (!text) {
    ElMessage.warning('没有可复制的内容')
    return
  }

  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`${label}已复制到剪贴板`)
  } catch (error) {
    console.error('复制失败:', error)
    // 备用方法
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      document.execCommand('copy')
      ElMessage.success(`${label}已复制到剪贴板`)
    } catch (err) {
      ElMessage.error('复制失败，请手动复制')
    }
    document.body.removeChild(textarea)
  }
}

const testSessionKey = (node) => {
  sessionForm.from_node = node
  sessionForm.to_node_id = ''
  sessionDialogVisible.value = true
}

const initiateSessionKey = async () => {
  if (!sessionForm.to_node_id) {
    ElMessage.warning('请选择目标节点')
    return
  }

  sessionLoading.value = true
  try {
    const response = await sessionKeysApi.initiate({
      node1_id: sessionForm.from_node.node_id,
      node2_id: sessionForm.to_node_id
    })

    if (response.code === 2000) {
      ElMessage.success('会话密钥分发发起成功')
      sessionDialogVisible.value = false
    } else {
      ElMessage.error(response.msg || '会话密钥分发失败')
    }
  } catch (error) {
    ElMessage.error('会话密钥分发失败')
    console.error('Error initiating session key:', error)
  } finally {
    sessionLoading.value = false
  }
}

const getStatusType = (status) => {
  const statusMap = {
    'registered': 'info',
    'kyber_uploaded': 'primary',
    'partial_key_received': 'warning',
    'falcon_generated': 'success',
    'active': 'success',
    'falcon_uploaded': 'success',
    'inactive': 'danger'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status) => {
  const statusMap = {
    'registered': '已注册',
    'kyber_uploaded': 'Kyber已上传',
    'partial_key_received': '部分私钥已接收',
    'falcon_generated': 'Falcon已生成',
    'active': '活跃',
    'falcon_uploaded': 'Falcon已上传',
    'inactive': '非活跃'
  }
  return statusMap[status] || status || '未知'
}

const getNodeTypeText = (nodeType) => {
  const typeMap = {
    'full': '全节点',
    'light': '轻节点',
    'validator': '验证节点',
    'storage': '存储节点',
    'compute': '计算节点'
  }
  return typeMap[nodeType] || nodeType
}

const formatDateTime = (datetime) => {
  if (!datetime) return '-'
  try {
    const date = new Date(datetime)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch (e) {
    return datetime
  }
}

// 删除节点
const deleteNode = async (node) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除节点 "${node.name}" (${node.node_id}) 吗？\n\n删除节点将同时删除以下关联数据：\n• 该节点的所有会话密钥\n• 该节点的所有交易记录\n• 该节点的所有消息记录\n• 该节点的Falcon密钥对\n• 该节点的密钥分发日志\n\n此操作不可撤销！`,
      '删除节点确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    // 设置删除状态
    node.deleting = true

    const response = await nodesApi.delete(node.id)
    if (response.code === 2000) {
      ElMessage.success(`节点 ${node.name} 删除成功`)

      // 显示删除的关联数据统计
      if (response.data && response.data.deleted_related_data) {
        const stats = response.data.deleted_related_data
        const statsText = [
          `会话密钥: ${stats.session_keys}`,
          `交易记录: ${stats.transactions}`,
          `消息记录: ${stats.messages}`,
          `Falcon密钥: ${stats.falcon_keys}`,
          `密钥分发日志: ${stats.key_logs}`
        ].join(', ')

        ElMessage.info(`同时删除了关联数据 - ${statsText}`)
      }

      // 刷新列表
      await getNodeList()
    } else {
      ElMessage.error(response.msg || '删除节点失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除节点失败:', error)
      ElMessage.error('删除节点失败')
    }
  } finally {
    // 清除删除状态
    node.deleting = false
  }
}

// 处理表格选择变化
const handleSelectionChange = (selection) => {
  selectedNodes.value = selection
}

// 取消选择
const clearSelection = () => {
  tableRef.value?.clearSelection()
  selectedNodes.value = []
}

// 批量删除节点
const batchDeleteNodes = async () => {
  if (selectedNodes.value.length === 0) {
    ElMessage.warning('请先选择要删除的节点')
    return
  }

  const nodeNames = selectedNodes.value.map(n => `"${n.name}" (${n.node_id})`).join('、')
  const nodeIds = selectedNodes.value.map(n => n.node_id)

  try {
    await ElMessageBox.confirm(
      `确定要删除以下 ${selectedNodes.value.length} 个节点吗？\n\n${nodeNames}\n\n删除节点将同时删除以下关联数据：\n• 所有会话密钥\n• 所有交易记录\n• 所有消息记录\n• 所有Falcon密钥对\n• 所有密钥分发日志\n\n此操作不可撤销！`,
      '批量删除节点确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    batchDeleting.value = true

    // 调用批量删除API
    const response = await nodesApi.batchDelete(nodeIds)

    if (response.code === 2000) {
      const data = response.data
      ElMessage.success(`成功删除 ${data.total_deleted_nodes} 个节点`)

      // 显示删除的关联数据统计
      if (data.total_deleted_related_data) {
        const stats = data.total_deleted_related_data
        const statsText = [
          `会话密钥: ${stats.session_keys}`,
          `交易记录: ${stats.transactions}`,
          `消息记录: ${stats.messages}`,
          `Falcon密钥: ${stats.falcon_keys}`,
          `密钥分发日志: ${stats.key_logs}`
        ].join(', ')

        ElMessage.info(`同时删除了关联数据 - ${statsText}`)
      }

      // 如果有未找到的节点，显示警告
      if (data.missing_nodes && data.missing_nodes.length > 0) {
        ElMessage.warning(`以下节点不存在: ${data.missing_nodes.join(', ')}`)
      }
    } else {
      ElMessage.error(response.msg || '批量删除节点失败')
    }

    // 清空选择并刷新列表
    clearSelection()
    await getNodeList()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量删除节点失败:', error)
      ElMessage.error('批量删除节点失败')
    }
  } finally {
    batchDeleting.value = false
  }
}

// 生成Falcon密钥
const generateFalconKeys = async (node) => {
  try {
    await ElMessageBox.confirm(
      `确定要为节点 "${node.name}" (${node.node_id}) 生成Falcon密钥吗？\n\n` +
      `此操作将：\n` +
      `• 生成无证书的Falcon密钥对\n` +
      `• 将公钥上传到区块链\n` +
      `• 供后续会话密钥分发使用\n\n` +
      `此操作可以安全重复执行！`,
      '生成Falcon密钥',
      {
        confirmButtonText: '确认生成',
        cancelButtonText: '取消',
        type: 'info'
      }
    )

    // 设置加载状态
    node.generatingFalcon = true

    const response = await nodesApi.generateFalconKeys(node.id)

    if (response.code === 2000) {
      ElMessage.success('Falcon密钥对生成成功')

      // 显示生成详情
      if (response.data) {
        const data = response.data
        let timingMessage = ''

        // 显示生成时间
        if (data.kyber_keygen_time) {
          timingMessage += `⏰ Kyber密钥生成时间: ${formatDateTime(data.kyber_keygen_time)}\n`
        }
        if (data.falcon_keygen_time) {
          timingMessage += `⏰ Falcon密钥生成时间: ${formatDateTime(data.falcon_keygen_time)}\n`
        }

        // 处理timing_info对象
        if (data.timing_info) {
          const timing = data.timing_info
          const totalTime = timing.total_time || 0

          // 构建详细的时间信息
          if (timing.load_partial_key_time !== undefined &&
              timing.falcon_keygen_time !== undefined &&
              timing.db_save_time !== undefined &&
              timing.blockchain_upload_time !== undefined) {
            timingMessage += `生成完整Falcon密钥对耗时: ${totalTime.toFixed(3)}秒 (` +
              `加载部分密钥: ${(timing.load_partial_key_time * 1000).toFixed(2)}ms, ` +
              `密钥生成: ${(timing.falcon_keygen_time * 1000).toFixed(2)}ms, ` +
              `数据库保存: ${(timing.db_save_time * 1000).toFixed(2)}ms, ` +
              `区块链上传: ${(timing.blockchain_upload_time * 1000).toFixed(2)}ms)`
          } else {
            timingMessage += `生成完整Falcon密钥对耗时: ${totalTime.toFixed(3)}秒`
          }
        } else if (data.generation_time !== undefined) {
          // 兼容旧版本的generation_time字段
          timingMessage += `生成完整Falcon密钥对耗时: ${data.generation_time.toFixed(3)}秒`
        } else {
          timingMessage += '生成完整Falcon密钥对成功'
        }

        ElMessage.info(timingMessage)
      }

      // 刷新节点列表
      getNodeList()
    } else {
      ElMessage.error(response.msg || 'Falcon密钥生成失败')
    }
  } catch (error) {
    if (error !== false) { // 不是用户取消
      console.error('Error generating Falcon keys:', error)
      ElMessage.error('生成Falcon密钥失败: ' + (error.message || '未知错误'))
    }
  } finally {
    node.generatingFalcon = false
  }
}

// 显示更新密钥对话框
const showUpdateKeysDialog = (node) => {
  currentUpdateNode.value = node
  // 重置表单
  Object.assign(updateKeysForm, {
    key_type: 'kyber',
    kyber_security_level: 512,
    falcon_security_level: 512,
    falcon_version: 'v2'  // 默认使用V2方案
  })
  updateKeysDialogVisible.value = true
}

// 确认更新密钥
const confirmUpdateKeys = async () => {
  try {
    // 表单验证
    const updateKeysFormRef = ref(null)
    if (updateKeysFormRef.value) {
      const valid = await updateKeysFormRef.value.validate()
      if (!valid) return
    }

    const node = currentUpdateNode.value
    if (!node) {
      ElMessage.error('未选择节点')
      return
    }

    // 确认对话框
    const keyTypeText = {
      'kyber': 'Kyber密钥',
      'falcon': 'Falcon密钥',
      'both': 'Kyber和Falcon密钥'
    }[updateKeysForm.key_type]

    const securityLevels = []
    if (updateKeysForm.key_type === 'kyber' || updateKeysForm.key_type === 'both') {
      securityLevels.push(`Kyber-${updateKeysForm.kyber_security_level}`)
    }
    if (updateKeysForm.key_type === 'falcon' || updateKeysForm.key_type === 'both') {
      const versionText = updateKeysForm.falcon_version === 'v1' ? 'V1(传统DLL)' : 'V2(无证书)'
      securityLevels.push(`Falcon-${updateKeysForm.falcon_security_level} ${versionText}`)
    }

    await ElMessageBox.confirm(
      `确定要为节点 "${node.name}" (${node.node_id}) 更新${keyTypeText}吗？\n\n` +
      `安全级别: ${securityLevels.join(', ')}\n\n` +
      `注意事项：\n` +
      `• 更新密钥会使现有的会话密钥失效\n` +
      `• 更新Kyber密钥会自动清除Falcon密钥\n` +
      `• 更新过程中节点可能暂时不可用\n\n` +
      `此操作不可撤销！`,
      '更新密钥确认',
      {
        confirmButtonText: '确认更新',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false
      }
    )

    updateKeysLoading.value = true
    updateKeysDialogVisible.value = false

    const response = await nodesApi.updateKeys(node.id, {
      key_type: updateKeysForm.key_type,
      kyber_security_level: updateKeysForm.kyber_security_level,
      falcon_security_level: updateKeysForm.falcon_security_level,
      falcon_version: updateKeysForm.falcon_version
    })

    if (response.code === 2000) {
      ElMessage.success(`${keyTypeText}更新成功`)

      // 显示更新详情
      if (response.data && response.data.data) {
        const data = response.data.data
        const details = []

        if (data.kyber) {
          details.push(`Kyber-${data.kyber.security_level}: 公钥${data.kyber.public_key_length}字节, 私钥${data.kyber.private_key_length}字节`)
        }
        if (data.falcon) {
          details.push(`Falcon-${data.falcon.security_level}: 公钥${data.falcon.public_key_length}字节, 私钥${data.falcon.private_key_length}字节`)
        }

        if (details.length > 0) {
          ElMessage.info(`密钥详情: ${details.join('; ')}`)
        }
      }

      // 刷新节点列表
      await getNodeList()
    } else {
      ElMessage.error(response.msg || '密钥更新失败')
    }

  } catch (error) {
    if (error !== 'cancel') {
      console.error('更新密钥失败:', error)
      ElMessage.error('密钥更新失败')
    }
  } finally {
    updateKeysLoading.value = false
    currentUpdateNode.value = null
  }
}

// 生命周期
onMounted(() => {
  // 1. 先获取当前活跃的区块链配置（静默模式，不弹提示）
  getCurrentBlockchainConfig(true)
  // 2. 然后获取节点列表（后端会自动只返回当前区块链的节点）
  getNodeList()

  // 3. 定期检查区块链配置是否已更改（防止在其他标签页切换配置）
  const intervalId = setInterval(async () => {
    try {
      const response = await blockchainApi.getActiveConfig()
      if (response.code === 2000 && response.data) {
        // 如果区块链配置ID发生了变化，自动重新加载
        if (response.data.id !== currentBlockchainId.value) {
          console.log(`🔔 检测到区块链配置已变更，自动刷新节点列表`)
          currentBlockchainConfig.value = response.data.name
          currentBlockchainId.value = response.data.id
          pagination.page = 1
          await getNodeList()
        }
      }
    } catch (error) {
      // 定时检查失败，不打印错误日志
    }
  }, 30000) // 每30秒检查一次

  // 组件卸载时清除定时器
  return () => {
    clearInterval(intervalId)
  }
})

// 监听当前区块链配置的变化，自动重新加载节点列表
watch(currentBlockchainId, async (newId, oldId) => {
  if (newId !== oldId && newId !== null) {
    console.log(`🔄 区块链配置已切换 (从 ${oldId} 到 ${newId})，正在重新加载节点列表...`)
    pagination.page = 1 // 重置到第一页
    await getNodeList()
  }
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.header-left {
  display: flex;
  align-items: center;
}

.ml-2 {
  margin-left: 8px;
}

.key-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
