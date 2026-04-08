<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="参数名称" prop="paramName">
        <el-input v-model="queryParams.paramName" placeholder="请输入参数名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd">获取公共参数</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="paramList">
      <el-table-column label="参数名称" align="center" prop="paramName" />
      <el-table-column label="参数值" align="center" prop="paramValue" :show-overflow-tooltip="true" />
      <el-table-column label="说明" align="center" prop="description" :show-overflow-tooltip="true" />
      <el-table-column label="创建时间" align="center" prop="creTime" />
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog title="获取公共参数" v-model="open" width="500px" append-to-body>
      <el-form ref="paramRef" :model="form" label-width="100px">
        <el-form-item label="加密算法类型" prop="encrytType">
          <el-select v-model="form.encrytType" placeholder="请选择加密算法类型" @change="handleTypeChange">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
            <el-option label="对称加密" value="对称加密" />
            <el-option label="非对称加密" value="非对称加密" />
            <el-option label="单向加密" value="单向加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法名称" prop="encrytName">
          <el-select v-model="form.encrytName" placeholder="请选择加密算法名称">
            <el-option v-for="option in encrytNameOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="submitForm">获取</el-button>
        <el-button @click="open = false">取 消</el-button>
      </template>
    </el-dialog>

    <el-dialog title="公共参数详情" v-model="detailOpen" width="700px" append-to-body destroy-on-close>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="椭圆曲线参数N">
          <div style="word-break: break-all; font-family: monospace;">{{ commonParams.N }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="椭圆曲线参数G">
          <div style="word-break: break-all; font-family: monospace;">{{ commonParams.G }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="椭圆曲线参数P">
          <div style="word-break: break-all; font-family: monospace;">{{ commonParams.P }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="系统公钥PPub">
          <div style="word-break: break-all; font-family: monospace;">{{ commonParams.PPub }}</div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="copyParams">复制所有参数</el-button>
        <el-button @click="detailOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="CommonParam">
import { getComParam } from "@/api/generate/keymanage"

const { proxy } = getCurrentInstance()
const paramList = ref([])
const open = ref(false)
const detailOpen = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)
const encrytNameOptions = ref([])
const commonParams = ref({})

const data = reactive({
  queryParams: { pageNum: 1, pageSize: 10, paramName: null },
  form: { encrytType: null, encrytName: null }
})

const { queryParams, form } = toRefs(data)

function getList() {
  loading.value = false
  paramList.value = [
    { paramName: '椭圆曲线N', paramValue: 'FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', description: 'SSCL椭圆曲线阶数', creTime: '-' },
    { paramName: '椭圆曲线G', paramValue: '32FF5C3C1980F218036E391C5D9C40F1B9F4094505050EA967986DDA9F075FC76C297A4B78817532007B00D75A4C3E9C7BD', description: 'SSCL椭圆曲线生成元', creTime: '-' },
    { paramName: '椭圆曲线P', paramValue: 'FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', description: 'SSCL椭圆曲线素数', creTime: '-' }
  ]
  total.value = 3
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm("queryRef"); handleQuery() }

function handleAdd() { reset(); open.value = true }

function reset() {
  form.value = { encrytType: null, encrytName: null }
  proxy.resetForm("paramRef")
}

function handleTypeChange(value) {
  if (value === '无证书非对称加密') { encrytNameOptions.value = [{ label: 'SM2', value: 'SM2' }, { label: 'SSCL', value: 'SSCL' }] }
  else if (value === '对称加密') { encrytNameOptions.value = [{ label: 'AES', value: 'AES' }] }
  else if (value === '非对称加密') { encrytNameOptions.value = [{ label: 'RSA', value: 'RSA' }, { label: 'ECC', value: 'ECC' }] }
  else if (value === '单向加密') { encrytNameOptions.value = [{ label: 'MD5', value: 'MD5' }] }
  else { encrytNameOptions.value = [] }
  form.value.encrytName = ''
}

function submitForm() {
  getComParam(form.value).then(response => {
    commonParams.value = response
    detailOpen.value = true
    open.value = false
  }).catch(() => {})
}

function copyParams() {
  const text = JSON.stringify(commonParams.value, null, 2)
  navigator.clipboard.writeText(text).then(() => { proxy.$modal.msgSuccess("参数已复制") }).catch(() => {})
}

getList()
</script>
