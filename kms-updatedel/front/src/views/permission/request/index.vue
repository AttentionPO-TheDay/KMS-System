<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryForm" size="small" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="申请用户" prop="userName">
        <el-input
          v-model="queryParams.userName"
          placeholder="请输入用户名"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="申请状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="请选择状态" clearable>
          <el-option label="待审批" value="0" />
          <el-option label="已通过" value="1" />
          <el-option label="已拒绝" value="2" />
          <el-option label="已使用并回退" value="3" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" size="small" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" size="small" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="requestList">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="申请ID" align="center" prop="requestId" width="80" />
      <el-table-column label="申请用户" align="center" prop="userName" width="120" />
      <el-table-column label="当前等级" align="center" width="100">
        <template #default="scope">
          <el-tag :type="levelTagType(scope.row.status === '1' ? scope.row.requestLevel : scope.row.originalLevel)">
            {{ levelText(scope.row.status === '1' ? scope.row.requestLevel : scope.row.originalLevel) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请等级" align="center" width="100">
        <template #default="scope">
          <el-tag :type="levelTagType(scope.row.requestLevel)">{{ levelText(scope.row.requestLevel) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请理由" align="center" prop="requestReason" :show-overflow-tooltip="true" />
      <el-table-column label="申请时间" align="center" prop="requestTime" width="180">
        <template #default="scope">
          <span>{{ parseTime(scope.row.requestTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="申请状态" align="center" prop="status" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.status === '0'" type="warning">待审批</el-tag>
          <el-tag v-else-if="scope.row.status === '1'" type="success">已通过</el-tag>
          <el-tag v-else-if="scope.row.status === '2'" type="danger">已拒绝</el-tag>
          <el-tag v-else-if="scope.row.status === '3'" type="info">已回退</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="审批人" align="center" prop="approveBy" width="120" />
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="180">
        <template #default="scope">
          <el-button
            v-if="scope.row.status === '0'"
            link
            type="primary"
            icon="Check"
            @click="handleApprove(scope.row)"
          >通过</el-button>
          <el-button
            v-if="scope.row.status === '0'"
            link
            type="danger"
            icon="Close"
            @click="handleReject(scope.row)"
          >拒绝</el-button>
          <el-button
            link
            type="info"
            icon="View"
            @click="handleView(scope.row)"
          >详情</el-button>
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

    <el-dialog :title="dialogTitle" v-model="approveDialogOpen" width="500px" append-to-body>
      <el-form ref="approveFormRef" :model="approveForm" :rules="approveRules" label-width="100px">
        <el-form-item label="申请用户">
          <el-input v-model="approveForm.userName" disabled />
        </el-form-item>
        <el-form-item label="申请等级">
          <el-tag :type="levelTagType(approveForm.requestLevel)">{{ levelText(approveForm.requestLevel) }}</el-tag>
        </el-form-item>
        <el-form-item label="申请理由">
          <el-input v-model="approveForm.requestReason" type="textarea" :rows="3" disabled />
        </el-form-item>
        <el-form-item label="审批备注" prop="approveNote">
          <el-input
            v-model="approveForm.approveNote"
            type="textarea"
            :rows="3"
            placeholder="请输入审批备注（可选）"
          />
        </el-form-item>
        <el-alert
          v-if="approveAction === 'approve'"
          title="注意：审批通过后，用户将临时获得该权限，操作完成后需手动或自动回退。"
          type="warning"
          :closable="false"
        />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitApprove">确 定</el-button>
          <el-button @click="approveDialogOpen = false">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog title="申请详情" v-model="detailDialogOpen" width="600px" append-to-body>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="申请ID">{{ currentRequest.requestId }}</el-descriptions-item>
        <el-descriptions-item label="申请用户">{{ currentRequest.userName }}</el-descriptions-item>
        <el-descriptions-item label="用户ID">{{ currentRequest.userId }}</el-descriptions-item>
        <el-descriptions-item label="原始等级">
          <el-tag :type="levelTagType(currentRequest.originalLevel)">{{ levelText(currentRequest.originalLevel) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="申请等级">
          <el-tag :type="levelTagType(currentRequest.requestLevel)">{{ levelText(currentRequest.requestLevel) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="是否临时">
          <el-tag v-if="currentRequest.isTemp === 1" type="success">是</el-tag>
          <el-tag v-else type="info">否</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="申请状态" :span="2">
          <el-tag v-if="currentRequest.status === '0'" type="warning">待审批</el-tag>
          <el-tag v-else-if="currentRequest.status === '1'" type="success">已通过</el-tag>
          <el-tag v-else-if="currentRequest.status === '2'" type="danger">已拒绝</el-tag>
          <el-tag v-else-if="currentRequest.status === '3'" type="info">已回退</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="申请理由" :span="2">
          {{ currentRequest.requestReason }}
        </el-descriptions-item>
        <el-descriptions-item label="申请时间" :span="2">
          {{ parseTime(currentRequest.requestTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="审批人" v-if="currentRequest.approveBy">
          {{ currentRequest.approveBy }}
        </el-descriptions-item>
        <el-descriptions-item label="审批时间" v-if="currentRequest.approveTime">
          {{ parseTime(currentRequest.approveTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="审批备注" :span="2" v-if="currentRequest.approveNote">
          {{ currentRequest.approveNote }}
        </el-descriptions-item>
        <el-descriptions-item label="使用时间" v-if="currentRequest.useTime">
          {{ parseTime(currentRequest.useTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="回退时间" v-if="currentRequest.rollbackTime">
          {{ parseTime(currentRequest.rollbackTime) }}
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

<script setup name="PermissionRequest">
import { listPermissionRequests, approveRequest, rejectRequest } from "@/api/permission/permission";

const { proxy } = getCurrentInstance();

/**
 * 权限等级文案与标签色。
 * Q2 / D13 已把角色收成 2 级：0=管理员、2=普通用户；
 * 历史上的 1=「中级用户」随 PUBLIC_KEY_LIST 功能一并废弃。
 * 这里用 `<= 0` 判定，避免再出现散落的 === 1 分支。
 */
function levelText(level) {
  return Number(level) <= 0 ? '管理员' : '普通用户';
}
function levelTagType(level) {
  return Number(level) <= 0 ? 'danger' : 'info';
}

const requestList = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);

const approveDialogOpen = ref(false);
const detailDialogOpen = ref(false);
const dialogTitle = ref("");
const approveAction = ref("");

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  userName: null,
  status: null
});

const approveForm = ref({
  requestId: null,
  userName: '',
  requestLevel: null,
  requestReason: '',
  approveNote: ''
});

const approveRules = {
  approveNote: [
    { max: 500, message: "审批备注长度不能超过500个字符", trigger: "blur" }  ]
};

const currentRequest = ref({});

function getList() {
  loading.value = true;
  listPermissionRequests(queryParams.value).then(response => {
    requestList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}

function resetQuery() {
  proxy.resetForm("queryForm");
  handleQuery();
}

function handleApprove(row) {
  approveForm.value = {
    requestId: row.requestId,
    userName: row.userName,
    requestLevel: row.requestLevel,
    requestReason: row.requestReason,
    approveNote: ''
  };
  dialogTitle.value = "审批通过";
  approveAction.value = "approve";
  approveDialogOpen.value = true;
}

function handleReject(row) {
  approveForm.value = {
    requestId: row.requestId,
    userName: row.userName,
    requestLevel: row.requestLevel,
    requestReason: row.requestReason,
    approveNote: ''
  };
  dialogTitle.value = "审批拒绝";
  approveAction.value = "reject";
  approveDialogOpen.value = true;
}

function handleView(row) {
  currentRequest.value = { ...row };
  detailDialogOpen.value = true;
}

function submitApprove() {
  proxy.$refs["approveFormRef"].validate(valid => {
    if (valid) {
      const data = {
        approveNote: approveForm.value.approveNote
      };

      const apiCall = approveAction.value === "approve"
        ? approveRequest(approveForm.value.requestId, data)
        : rejectRequest(approveForm.value.requestId, data);

      apiCall.then(response => {
        proxy.$modal.msgSuccess(`审批${approveAction.value === "approve" ? "通过" : "拒绝"}成功`);
        approveDialogOpen.value = false;
        getList();
      }).catch(error => {
        proxy.$modal.msgError("审批失败：" + error.message);
      });
    }
  });
}

getList();
</script>
