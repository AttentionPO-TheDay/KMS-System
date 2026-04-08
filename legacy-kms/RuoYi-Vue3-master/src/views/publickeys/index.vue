<template>
  <div class="app-container">
    <el-alert
      title="公共密钥查看页面"
      type="info"
      :closable="false"
      style="margin-bottom: 20px;"
    >
      <template #default>
        <p>您可以在此查看所有公开的密钥信息（不包括私钥）</p>
        <el-button 
          v-if="showRollbackButton" 
          type="warning" 
          size="small" 
          icon="RefreshLeft"
          @click="handleRollback"
          style="margin-top: 10px;"
        >
          操作完成，回退权限
        </el-button>
      </template>
    </el-alert>

    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="用户名" prop="userName">
        <el-input
          v-model="queryParams.userName"
          placeholder="请输入用户名"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="加密算法" prop="encrytName">
        <el-input
          v-model="queryParams.encrytName"
          placeholder="请输入加密算法名称"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="keyList">
      <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="加密类型" align="center" prop="encrytType" width="120" />
      <el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
      <el-table-column label="密钥用途" align="center" prop="keyUse" width="120" />
      <el-table-column label="公钥值" align="center" prop="keyValue" :show-overflow-tooltip="true" min-width="200">
        <template #default="scope">
          <el-tooltip :content="scope.row.keyValue" placement="top">
            <span class="key-value">{{ scope.row.keyValue }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" align="center" prop="creTime" width="160">
        <template #default="scope">
          <span>{{ parseTime(scope.row.creTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="100">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="View"
            @click="handleView(scope.row)"
          >查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <!-- 查看详情对话框 -->
    <el-dialog title="公钥详细信息" v-model="detailDialogOpen" width="700px" append-to-body>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="密钥ID">{{ currentKey.keyId }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ currentKey.userName }}</el-descriptions-item>
        <el-descriptions-item label="加密类型">{{ currentKey.encrytType }}</el-descriptions-item>
        <el-descriptions-item label="加密算法">{{ currentKey.encrytName }}</el-descriptions-item>
        <el-descriptions-item label="密钥名称" :span="2">{{ currentKey.keyName }}</el-descriptions-item>
        <el-descriptions-item label="密钥用途" :span="2">{{ currentKey.keyUse }}</el-descriptions-item>
        <el-descriptions-item label="公钥值" :span="2">
          <el-input
            v-model="currentKey.keyValue"
            type="textarea"
            :rows="6"
            readonly
          />
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ parseTime(currentKey.creTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ parseTime(currentKey.updTime) }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="detailDialogOpen = false">关 闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="PublicKeys">
import { listKeymanage } from "@/api/keymanage/keymanage";
import { listPermissionRequests, rollbackPermission as apiRollbackPermission } from "@/api/permission/permission";
import useUserStore from '@/store/modules/user';

const { proxy } = getCurrentInstance();
const userStore = useUserStore();

const keyList = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const detailDialogOpen = ref(false);
const currentKey = ref({});
const showRollbackButton = ref(false);
const currentRequestId = ref(null);

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  userName: null,
  encrytName: null,
  keyName: null
});

/** 查询公钥列表 */
function getList() {
  loading.value = true;
  listKeymanage(queryParams.value).then(response => {
    keyList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}

/** 查看详情 */
function handleView(row) {
  currentKey.value = { ...row };
  detailDialogOpen.value = true;
}

/** 检查是否有待回退的权限 */
function checkPendingRollback() {
  if (userStore.roleLevel === 1) {
    listPermissionRequests({
      userId: userStore.id,
      status: '1'
    }).then(response => {
      if (response.rows && response.rows.length > 0) {
        const approvedRequest = response.rows[0];
        if (approvedRequest.isTemp === 1) {
          currentRequestId.value = approvedRequest.requestId;
          showRollbackButton.value = true;
        }
      }
    });
  }
}

/** 回退权限 */
function handleRollback() {
  if (!currentRequestId.value) {
    proxy.$modal.msgWarning("没有可回退的权限申请");
    return;
  }
  
  console.log('[PublicKeys] 开始回退权限，requestId:', currentRequestId.value);
  console.log('[PublicKeys] 回退前 roleLevel:', userStore.roleLevel);
  
  proxy.$modal.confirm('确认回退到普通用户权限？').then(() => {
    apiRollbackPermission(currentRequestId.value).then(response => {
      console.log('[PublicKeys] 回退API调用成功:', response);
      proxy.$modal.msgSuccess("权限已回退成功！即将返回用户密钥页面...");
      showRollbackButton.value = false;
      currentRequestId.value = null;
      
      console.log('[PublicKeys] 调用 userStore.getInfo() 刷新用户信息');
      userStore.getInfo().then(() => {
        console.log('[PublicKeys] getInfo() 完成，新的 roleLevel:', userStore.roleLevel);
        setTimeout(() => {
          console.log('[PublicKeys] 准备跳转到 userKeys 并刷新页面');
          proxy.$router.push({ path: '/userKeys' }).then(() => {
            window.location.reload();
          });
        }, 1000);
      });
    }).catch(error => {
      console.error('[PublicKeys] 回退失败:', error);
      proxy.$modal.msgError("回退失败：" + error.message);
    });
  }).catch(() => {
    console.log('[PublicKeys] 用户取消回退');
  });
}

// 页面加载时检查权限和待回退状态
onMounted(() => {
  console.log('[PublicKeys] onMounted - 当前 roleLevel:', userStore.roleLevel);
  console.log('[PublicKeys] onMounted - 用户:', userStore.name, '用户ID:', userStore.id);
  
  if (userStore.roleLevel > 1) {
    console.log('[PublicKeys] 权限不足，roleLevel =', userStore.roleLevel, '跳转到 userKeys');
    proxy.$message.warning('您没有权限访问此页面');
    proxy.$router.push({ path: '/userKeys' });
    return;
  }
  
  console.log('[PublicKeys] 权限检查通过，roleLevel =', userStore.roleLevel);
  checkPendingRollback();
  getList();
});
</script>

<style scoped>
.key-value {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #409EFF;
  cursor: pointer;
}

.el-alert {
  margin-bottom: 20px;
}
</style>
