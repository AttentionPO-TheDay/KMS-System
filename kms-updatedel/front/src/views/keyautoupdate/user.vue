<template>
  <div class="app-container">
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
          <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
            {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '已启用' : '未启用' }}
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
import { listKeymanage, updateKeyAutoUpdate } from "@/api/lifecycle/lifecycle";
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

function getList() {
  loading.value = true;
  listKeymanage(queryParams.value).then(response => {
    keyList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}

function handleToggleAutoUpdate(row) {
  const newStatus = isAutoUpdateEnabled(row.autoUpdate) ? '0' : '1';
  const statusText = newStatus === '1' ? '启用' : '禁用';

  proxy.$modal.confirm(`确认${statusText}密钥"${row.keyName}"的自动更新功能？`).then(() => {
      const updateData = {
        keyId: row.keyId,
        autoUpdate: newStatus
    };

    updateKeyAutoUpdate(updateData).then(() => {
      proxy.$modal.msgSuccess(`已${statusText}自动更新`);
      getList();
    });
  }).catch(() => {});
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function checkPendingRollback() {
  if (userStore.roleLevel === 0) {
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

function handleRollback() {
  if (!currentRequestId.value) {
    proxy.$modal.msgWarning("没有可回退的权限申请");
    return;
  }

  proxy.$modal.confirm('确认回退到普通用户权限？').then(() => {
    apiRollbackPermission(currentRequestId.value).then(response => {
      proxy.$modal.msgSuccess("权限已回退成功！");
      showRollbackButton.value = false;
      currentRequestId.value = null;

      userStore.getInfo().then(() => {
        setTimeout(() => {
          proxy.$router.push({ path: '/index' }).then(() => {
            window.location.reload();
          });
        }, 1000);
      });
    }).catch(error => {
      proxy.$modal.msgError("回退失败：" + error.message);
    });
  }).catch(() => {});
}

onMounted(() => {
  if (userStore.roleLevel > 0) {
    proxy.$message.warning('您没有权限访问此页面');
    // 路径不带 /updatedel 前缀：router 的 base 会自动拼接，手写前缀会翻倍成 404。
    proxy.$router.push({ path: '/index' });
    return;
  }
  checkPendingRollback();
  getList();
});
</script>

<style scoped>
.el-alert {
  margin-bottom: 20px;
}
</style>
