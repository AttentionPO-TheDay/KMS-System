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
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['keymanage:keymanage:edit']"
          style="padding: 6px 12px; margin-top: 15px;"
        >修改密钥自动更新状态</el-button>
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

    <!-- 添加或修改密钥管理对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="用户ID" prop="userId">
          <el-input v-model="form.userId" placeholder="请输入用户ID" />
        </el-form-item>
        <el-form-item label="用户名" prop="userName">
          <el-input v-model="form.userName" placeholder="请输入用户名" />
        </el-form-item>

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
        <!-- <el-form-item label="密钥值" prop="keyValue">
          <el-input v-model="form.keyValue" placeholder="请输入密钥值" />
        </el-form-item> -->
        <!-- <el-form-item label="创建时间" prop="creTime">
          <el-input v-model="form.creTime" placeholder="请输入创建时间" />
        </el-form-item>
        <el-form-item label="更新时间" prop="updTime">
          <el-input v-model="form.updTime" placeholder="请输入更新时间" />
        </el-form-item> -->
        <el-form-item label="密钥自动更新状态" prop="autoUpdate">
          <el-input v-model="form.autoUpdate" placeholder="请输入密钥自动更新状态" />
        </el-form-item>
        <el-form-item label="密钥工作状态" prop="status">
          <el-input v-model="form.status" placeholder="请输入密钥工作状态" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="Keymanage">
import { listKeymanage, getKeymanage, delKeymanage, addKeymanage, updateKeymanage } from "@/api/keymanage/keymanage";

const { proxy } = getCurrentInstance();

const keymanageList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const single = ref(true);
const multiple = ref(true);
const total = ref(0);
const title = ref("");

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

// /** 提交按钮 */
// function submitForm() {
//   proxy.$refs["keymanageRef"].validate(valid => {
//     if (valid) {
//       if (form.value.keyId != null) {
//         updateKeymanage(form.value).then(response => {
//           proxy.$modal.msgSuccess("修改成功");
//           open.value = false;
//           getList();
//         });
//       } else {
//         addKeymanage(form.value).then(response => {
//           proxy.$modal.msgSuccess("新增成功");
//           open.value = false;
//           getList();
//         });
//       }
//     }
//   });
// }
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
            { label: 'SM2', value: 'SM2' }
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
