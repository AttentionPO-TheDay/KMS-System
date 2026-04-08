<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input
          v-model="queryParams.userId"
          placeholder="请输入用户ID"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input
          v-model="queryParams.userName"
          placeholder="请输入用户名"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="加密算法名称" prop="encrytName">
        <el-input
          v-model="queryParams.encrytName"
          placeholder="请输入加密算法名称"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input
          v-model="queryParams.keyName"
          placeholder="请输入密钥名称"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="密钥用途" prop="keyUse">
        <el-input
          v-model="queryParams.keyUse"
          placeholder="请输入密钥用途"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="密钥值" prop="keyValue">
        <el-input
          v-model="queryParams.keyValue"
          placeholder="请输入密钥值"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="创建时间" prop="creTime">
        <el-input
          v-model="queryParams.creTime"
          placeholder="请输入创建时间"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="更新时间" prop="updTime">
        <el-input
          v-model="queryParams.updTime"
          placeholder="请输入更新时间"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="密钥自动更新状态" prop="autoUpdate">
        <el-input
          v-model="queryParams.autoUpdate"
          placeholder="请输入密钥自动更新状态"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Plus"
          @click="handleAdd"
          v-hasPermi="['keymanage:keymanage:add']"
          style="padding: 6px 12px; margin-top: 15px;"
        >密钥生成</el-button>
      </el-col> 
          
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <!-- <el-table-column label="用户名" align="center" prop="userName" /> -->
      <el-table-column label="加密算法类型" align="center" prop="encrytType" />
      <el-table-column label="加密算法名称" align="center" prop="encrytName" />
      <el-table-column label="密钥名称" align="center" prop="keyName" />
      <el-table-column label="密钥用途" align="center" prop="keyUse" />
      <!-- <el-table-column label="密钥值" align="center" prop="keyValue" /> -->
      <el-table-column label="创建时间" align="center" prop="creTime" />
      <el-table-column label="更新时间" align="center" prop="updTime" />
      <el-table-column label="密钥自动更新状态" align="center" prop="autoUpdate" />

      <el-table-column label="操作" align="center" width="150">
        <template #default="scope">
          <el-button
            type="primary"
            link
            icon="View"
            @click="handleViewDetails(scope.row)"
          >详情</el-button>

          </template>
      </el-table-column>
      <!-- <el-table-column label="密钥工作状态" align="center" prop="status" /> -->
      <!-- <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['keymanage:keymanage:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['keymanage:keymanage:remove']">删除</el-button>
        </template>
      </el-table-column> -->
    </el-table>
    
    <pagination
      v-show="total>0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="选择用户" prop="userId">
          <el-select v-model="form.userId" placeholder="请选择用户" filterable>
            <el-option
              v-for="user in userList"
              :key="user.userId"
              :label="`${user.userName} (ID: ${user.userId})`"
              :value="user.userId"
            />
          </el-select>
        </el-form-item>
        <!-- <el-form-item label="用户名" prop="userName">
          <el-input v-model="form.userName" placeholder="请输入用户名" />
        </el-form-item> -->

        <el-form-item label="加密算法类型" prop="encrytType">
          <el-select v-model="form.encrytType" placeholder="请选择加密算法类型" @change="handleEncrytTypeChange">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
            <el-option label="对称加密" value="对称加密" />
            <el-option label="非对称加密" value="非对称加密" />
            <el-option label="单向加密" value="单向加密" />
          </el-select>
        </el-form-item>

        <el-form-item label="加密算法名称" prop="encrytName">
          <el-select v-model="form.encrytName" placeholder="请选择加密算法名称">
            <el-option
              v-for="option in encrytNameOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="form.keyName" placeholder="请输入密钥名称" />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="form.keyUse" placeholder="请输入密钥用途" />
        </el-form-item>
        <el-form-item label="密钥所属域(SSCL)" prop="keyDomain">
          <el-input v-model="form.keyDimain" placeholder="请输入密钥所属域" />
        </el-form-item>
        <!-- <el-form-item label="密钥值" prop="keyValue">
          <el-input v-model="form.keyValue" placeholder="请输入密钥值" />
        </el-form-item> -->
        <!-- <el-form-item label="创建时间" prop="creTime">
          <el-input v-model="form.creTime" placeholder="请输入创建时间" />
        </el-form-item>
        <el-form-item label="更新时间" prop="updTime">
          <el-input v-model="form.updTime" placeholder="请输入更新时间" />
        </el-form-item> -->
        <!-- <el-form-item label="密钥自动更新状态" prop="autoUpdate">
          <el-input v-model="form.autoUpdate" placeholder="请输入密钥自动更新状态" />
        </el-form-item>
        <el-form-item label="密钥工作状态" prop="status">
          <el-input v-model="form.status" placeholder="请输入密钥工作状态" />
        </el-form-item> -->
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog title="密钥详细信息" v-model="detailOpen" width="700px" append-to-body destroy-on-close>
      <div class="detail-container">
        <el-divider content-position="left">基础信息</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="密钥ID">
            <el-tag type="info">{{ detailInfo.keyId }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ detailInfo.keyName }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ detailInfo.userId }}</el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="detailInfo.autoUpdate === 'true' ? 'success' : 'warning'">
              {{ detailInfo.autoUpdate === 'true' ? '自动更新' : '手动更新' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="加密类型">
            <el-tag effect="dark">{{ detailInfo.encrytName }}</el-tag>
            <span style="margin-left:8px; font-size:12px; color:#999">({{ detailInfo.encrytType }})</span>
          </el-descriptions-item>
          <el-descriptions-item label="密钥用途">{{ detailInfo.keyUse }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailInfo.creTime }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detailInfo.updTime }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">核心数据</el-divider>

        <div class="key-content-box">
          <template v-if="detailInfo.encrytName === 'SM2'">
            <div class="key-item">
              <span class="key-label">部分私钥 (Partial Key):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.partialKey || '无数据' }}</div>
            </div>
            <div class="key-item">
              <span class="key-label">声明公钥 (Public Key Declaration):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.finalPublicKey || '无数据' }}</div>
            </div>
          </template>

          <template v-else-if="detailInfo.encrytName === 'SSCL'">
            <div class="key-item">
              <span class="key-label">SS份额 (SS Share):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.SSCLKey || '无数据' }}</div>
            </div>
            <div class="key-item">
              <span class="key-label">密钥所属域 (Domain):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.SSCLDomian || detailInfo.keyDimain || '无数据' }}</div>
            </div>
          </template>

          <template v-else>
             <div class="key-item">
              <span class="key-label">密钥原始值 (Key Value):</span>
              <div class="key-value-block">{{ detailInfo.keyValue }}</div>
            </div>
          </template>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="copyDetailInfo">一键复制信息</el-button>
          <el-button @click="detailOpen = false">关 闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="Keymanage">
import { listKeymanage, getKeymanage, delKeymanage, addKeymanage, updateKeymanage } from "@/api/keymanage/keymanage";
import { getCurrentInstance, reactive, ref, toRefs } from 'vue';
import { listNonAdminUsers } from "@/api/system/user";
import useUserStore from '@/store/modules/user';

const { proxy } = getCurrentInstance();
const userStore = useUserStore();

const keymanageList = ref([]);
const userList = ref([]);  // 用户列表
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const single = ref(true);
const multiple = ref(true);
const total = ref(0);
const title = ref("");

// ---- 新增变量 ----
const detailOpen = ref(false);
const detailInfo = ref({});

const data = reactive({
  form: {},
  encrytNameOptions: [],
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    userName: null,
    encrytType: null,
    encrytName: null,
    keyName: null,
    keyUse: null,
    keyValue: null,
    creTime: null,
    updTime: null,
    autoUpdate: null,
    status: null
  },
  rules: {
    userId: [
      { required: true, message: "用户ID不能为空", trigger: "blur" }
    ],
    userName: [
      { required: true, message: "用户名不能为空", trigger: "blur" }
    ],
    encrytType: [
      { required: true, message: "加密算法类型不能为空", trigger: "change" }
    ],
    encrytName: [
      { required: true, message: "加密算法名称不能为空", trigger: "blur" }
    ],
    keyName: [
      { required: true, message: "密钥名称不能为空", trigger: "blur" }
    ],
    keyUse: [
      { required: true, message: "密钥用途不能为空", trigger: "blur" }
    ],
    keyValue: [
      { required: true, message: "密钥值不能为空", trigger: "blur" }
    ],
    creTime: [
      { required: true, message: "创建时间不能为空", trigger: "blur" }
    ],
    updTime: [
      { required: true, message: "更新时间不能为空", trigger: "blur" }
    ],
    autoUpdate: [
      { required: true, message: "密钥自动更新状态不能为空", trigger: "blur" }
    ],
    status: [
      { required: true, message: "密钥工作状态不能为空", trigger: "change" }
    ]
  }
});

const { queryParams, encrytNameOptions, form, rules } = toRefs(data);

// 计算当前登录用户是否为管理员
const isCurrentUserAdmin = computed(() => {
  return userStore.roleLevel === 0;
});

/** 查询密钥管理列表 */
function getList() {
  loading.value = true;
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

// 取消按钮
function cancel() {
  open.value = false;
  reset();
}

// 表单重置
function reset() {
  form.value = {
    keyId: null,
    userId: null,
    userName: 'null',
    encrytType: null,
    encrytName: null,
    keyName: null,
    keyUse: null,
    keyValue: null,
    creTime: null,
    updTime: null,
    autoUpdate: 'false',
    status: 'null'
  };
  proxy.resetForm("keymanageRef");
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

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.keyId);
  single.value = selection.length != 1;
  multiple.value = !selection.length;
}

/** 新增按钮操作 */
function handleAdd() {
  reset();
  // 获取非管理员用户列表
  listNonAdminUsers().then(response => {
    userList.value = response.data || [];
  });
  open.value = true;
  title.value = "添加密钥管理";
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset();
  const _keyId = row.keyId || ids.value
  getKeymanage(_keyId).then(response => {
    form.value = response.data;
    open.value = true;
    title.value = "修改密钥管理";
  });
}

/** * 查看详情操作
 * (原 downloadTxt 修改为展示弹窗)
 */
function handleViewDetails(row) {
  // 1. 复制行数据
  const info = { ...row };

  // 2. 尝试解析 keyValue 里的 JSON
  try {
    const parsed = JSON.parse(row.keyValue || '{}');
    info.parsedKey = parsed;
  } catch (e) {
    // 如果解析失败，说明不是JSON，或者是普通字符串
    info.parsedKey = {};
    console.warn("Key value is not JSON", e);
  }

  // 3. 赋值并打开窗口
  detailInfo.value = info;
  detailOpen.value = true;
}

/** 复制详情信息到剪贴板 */
function copyDetailInfo() {
  const info = detailInfo.value;
  let textToCopy = `密钥详情导出\n----------------\n`;
  textToCopy += `KeyID: ${info.keyId}\nName: ${info.keyName}\nUserID: ${info.userId}\nType: ${info.encrytName}\n`;

  if (info.encrytName === 'SM2') {
    textToCopy += `Partial Key: ${info.parsedKey?.partialKey}\n`;
    textToCopy += `Public Key: ${info.parsedKey?.finalPublicKey}`;
  } else if (info.encrytName === 'SSCL') {
    textToCopy += `Share: ${info.parsedKey?.SSCLKey}\n`;
    textToCopy += `Domain: ${info.parsedKey?.SSCLDomian}`;
  } else {
    textToCopy += `Key Value: ${info.keyValue}`;
  }

  // 执行复制
  navigator.clipboard.writeText(textToCopy).then(() => {
    proxy.$modal.msgSuccess("信息已复制到剪贴板");
  }).catch(() => {
    proxy.$modal.msgError("复制失败，请手动复制");
  });
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["keymanageRef"].validate(valid => {
    if (valid) {
      if (form.value.keyId != null) {
        if(form.value.encrytType=="无证书非对称加密"){
          alert("该功能需配合用户系统使用")
        }
        else{
        updateKeymanage(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功");
          open.value = false;
          getList();
        });}
      } else {
        if(form.value.encrytType=="无证书非对称加密"){
          alert("该功能需配合用户系统使用")
        }
        else{
        addKeymanage(form.value).then(response => {
          proxy.$modal.msgSuccess("新增成功");
          open.value = false;
          getList();
        });}
      }
    }
  });
}

/** 删除按钮操作 */
function handleDelete(row) {
  const _keyIds = row.keyId || ids.value;
  proxy.$modal.confirm('是否确认删除密钥管理编号为"' + _keyIds + '"的数据项？').then(function() {
    return delKeymanage(_keyIds);
  }).then(() => {
    getList();
    proxy.$modal.msgSuccess("删除成功");
  }).catch(() => {});
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('keymanage/keymanage/export', {
    ...queryParams.value
  }, `keymanage_${new Date().getTime()}.xlsx`)
}

function handleEncrytTypeChange(value) {
      if (value === '无证书非对称加密') {
        encrytNameOptions.value = [
            { label: 'SM2', value: 'SM2' },
            { label: 'SSCL', value: 'SSCL'}
        ];
      } else if (value === '对称加密') {
        // 对称加密选项
        encrytNameOptions.value = [
          { label: 'AES', value: 'AES' }
        ];
      } else if (value === '非对称加密') {
        // 非对称加密选项
        encrytNameOptions.value = [
          { label: 'RSA', value: 'RSA' },
          { label: 'ECC', value: 'ECC' }
        ];
      } else if (value === '单向加密') {
        // 单向加密选项
        encrytNameOptions.value = [
          { label: 'MD5', value: 'MD5' },
          { label: 'BLAKE2', value: 'BLAKE2' },
          { label: 'SHA-256', value: 'SHA-256' },
          { label: 'SHA-512', value: 'SHA-512' },
          { label: 'SHA-3', value: 'SHA-3' }
        ];
      } else {
        // 清空选项
        encrytNameOptions.value = [];
      }
      // 清空已选的加密算法名称
      form.value.encrytName = '';
    }

getList();
</script>

<style scoped>
/* 详情弹窗样式美化 */
.detail-container {
  padding: 0 10px;
}

/* 核心数据区域样式 */
.key-content-box {
  background-color: #f8f9fa;
  border-radius: 4px;
  padding: 15px;
  margin-top: 10px;
  border: 1px solid #ebeef5;
}

.key-item {
  margin-bottom: 15px;
}

.key-item:last-child {
  margin-bottom: 0;
}

.key-label {
  display: block;
  font-weight: bold;
  color: #606266;
  margin-bottom: 5px;
  font-size: 14px;
}

/* 模拟代码块的深色背景样式 */
.key-value-block {
  background-color: #282c34; /* 深色背景 */
  color: #abb2bf;             /* 浅色字体 */
  padding: 10px;
  border-radius: 4px;
  font-family: Consolas, Monaco, monospace; /* 等宽字体 */
  font-size: 13px;
  word-break: break-all;      /* 强制长单词换行 */
  white-space: pre-wrap;      /* 保留格式 */
  line-height: 1.5;
  box-shadow: inset 0 0 6px rgba(0,0,0,0.1);
}

/* 调整 el-descriptions 的标签宽度 */
:deep(.el-descriptions__label) {
  width: 120px;
  font-weight: bold;
}
</style>