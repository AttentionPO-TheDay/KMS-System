<template>
  <div class="app-container">
    <el-alert
      title="密钥自动更新管理"
      type="info"
      :closable="false"
      style="margin-bottom: 20px;"
    >
      <template #default>
        <p>您可以在此管理密钥的自动更新状态</p>
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
      <el-form-item label="密钥名称" prop="keyName">
        <el-input
          v-model="queryParams.keyName"
          placeholder="请输入密钥名称"
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
      <el-table-column label="自动更新状态" align="center" prop="autoUpdate" width="120">
        <template #default="scope">
          <el-tag :type="scope.row.autoUpdate === 1 ? 'success' : 'info'">
            {{ scope.row.autoUpdate === 1 ? '已启用' : '未启用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" align="center" prop="creTime" width="160">
        <template #default="scope">
          <span>{{ parseTime(scope.row.creTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="150">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Edit"
            @click="handleToggleAutoUpdate(scope.row)"
          >切换状态</el-button>
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
  </div>
</template>

<script setup name="KeyAutoUpdateUser">
import { listKeymanage, updateKeymanage } from "@/api/keymanage/keymanage";
import { listPermissionRequests, rollbackPermission as apiRollbackPermission } from "@/api/permission/permission";
import useUserStore from '@/store/modules/user';

const { proxy } = getCurrentInstance();
const userStore = useUserStore();

const keyList = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const showRollbackButton = ref(false);
const currentRequestId = ref(null);

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  keyName: null
});

/** 查询密钥列表 */
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

/** 切换自动更新状态 */
function handleToggleAutoUpdate(row) {
  const newStatus = row.autoUpdate === 1 ? 0 : 1;
  const statusText = newStatus === 1 ? '启用' : '禁用';
  
  proxy.$modal.confirm(`确认${statusText}密钥"${row.keyName}"的自动更新功能？`).then(() => {
    const updateData = {
      keyId: row.keyId,
      autoUpdate: newStatus
    };
    
    updateKeymanage(updateData).then(() => {
      proxy.$modal.msgSuccess(`已${statusText}自动更新`);
      getList();
    });
  }).catch(() => {});
}

/** 检查是否有待回退的权限 */
function checkPendingRollback() {
  // 如果用户是管理员（role_level=0），检查是否有待回退的申请
  if (userStore.roleLevel === 0) {
    listPermissionRequests({
      userId: userStore.id,
      status: '1'  // 已通过的申请
    }).then(response => {
      if (response.rows && response.rows.length > 0) {
        const approvedRequest = response.rows[0];
        if (approvedRequest.isTemp === 1) {
          // 找到临时权限申请，显示回退按钮
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
  
  console.log('[KeyAutoUpdate-User] 开始回退权限，requestId:', currentRequestId.value);
  console.log('[KeyAutoUpdate-User] 回退前 roleLevel:', userStore.roleLevel);
  
  proxy.$modal.confirm('确认回退到普通用户权限？').then(() => {
    apiRollbackPermission(currentRequestId.value).then(response => {
      console.log('[KeyAutoUpdate-User] 回退API调用成功:', response);
      proxy.$modal.msgSuccess("权限已回退成功！即将返回用户密钥页面...");
      showRollbackButton.value = false;
      currentRequestId.value = null;
      
      console.log('[KeyAutoUpdate-User] 调用 userStore.getInfo() 刷新用户信息');
      userStore.getInfo().then(() => {
        console.log('[KeyAutoUpdate-User] getInfo() 完成，新的 roleLevel:', userStore.roleLevel);
        setTimeout(() => {
          console.log('[KeyAutoUpdate-User] 准备跳转到 userKeys 并刷新页面');
          proxy.$router.push({ path: '/userKeys' }).then(() => {
            window.location.reload();
          });
        }, 1000);
      });
    }).catch(error => {
      console.error('[KeyAutoUpdate-User] 回退失败:', error);
      proxy.$modal.msgError("回退失败：" + error.message);
    });
  }).catch(() => {
    console.log('[KeyAutoUpdate-User] 用户取消回退');
  });
}

// 页面加载时检查权限和待回退状态
onMounted(() => {
  console.log('[KeyAutoUpdate-User] onMounted - 当前 roleLevel:', userStore.roleLevel);
  console.log('[KeyAutoUpdate-User] onMounted - 用户:', userStore.name, '用户ID:', userStore.id);
  
  // 检查用户权限 - 需要管理员权限 (role_level=0)
  if (userStore.roleLevel > 0) {
    console.log('[KeyAutoUpdate-User] 权限不足，roleLevel =', userStore.roleLevel, '跳转到 userKeys');
    proxy.$message.warning('您没有权限访问此页面');
    proxy.$router.push({ path: '/userKeys' });
    return;
  }
  
  console.log('[KeyAutoUpdate-User] 权限检查通过，roleLevel =', userStore.roleLevel);
  checkPendingRollback();
  getList();
});
</script>

<style scoped>
.el-alert {
  margin-bottom: 20px;
}
</style>
