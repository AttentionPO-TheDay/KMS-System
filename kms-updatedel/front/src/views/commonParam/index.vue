<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="算法名称" prop="encrytName">
        <el-input v-model="queryParams.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="所属域" prop="keyDomain">
        <el-input v-model="queryParams.keyDomain" placeholder="请输入所属域" clearable @keyup.enter="handleQuery" />
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

    <el-table v-loading="loading" :data="paramList" tooltip-effect="light">
      <el-table-column label="算法名称" align="center" prop="algorithm" width="120" />
      <el-table-column label="所属域" align="center" prop="domain" width="100" />
      <el-table-column label="参数名称" align="center" prop="label" width="180" />
      <el-table-column label="参数值" align="center" prop="value" :show-overflow-tooltip="true" />
      <el-table-column label="说明" align="center" prop="description" min-width="180" show-overflow-tooltip />
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog title="获取公共参数" v-model="open" width="500px" append-to-body>
      <el-form ref="paramRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="加密算法类型" prop="encrytType">
          <el-select v-model="form.encrytType" placeholder="请选择加密算法类型" @change="handleTypeChange" style="width: 100%">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法名称" prop="encrytName">
          <el-select v-model="form.encrytName" placeholder="请选择加密算法名称" style="width: 100%">
            <el-option v-for="option in encrytNameOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain">
          <el-input v-model="form.keyDomain" placeholder="默认 A" maxlength="32" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="submitForm">获取</el-button>
        <el-button @click="open = false">取 消</el-button>
      </template>
    </el-dialog>

    <el-dialog :title="`${detailTitle}公共参数详情`" v-model="detailOpen" width="760px" append-to-body destroy-on-close>
<el-descriptions :column="1" border>
        <el-descriptions-item v-for="item in currentItems" :key="item.key" :label="item.label">
          <div class="param-value">{{ item.value || '-' }}</div>
          <div class="param-desc">{{ item.description }}</div>
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
import { getComParam } from '@/api/generate/keymanage'

const { proxy } = getCurrentInstance()
const paramList = ref([])
const open = ref(false)
const detailOpen = ref(false)
const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const encrytNameOptions = ref([])
const currentItems = ref([])
const detailAlgorithm = ref('')
const detailDomain = ref('A')

const data = reactive({
  queryParams: { pageNum: 1, pageSize: 10, encrytName: null, keyDomain: null },
  form: { encrytType: '无证书非对称加密', encrytName: 'SM2', keyDomain: 'A' },
  rules: {
    encrytType: [{ required: true, message: '请选择加密算法类型', trigger: 'change' }],
    encrytName: [{ required: true, message: '请选择加密算法名称', trigger: 'change' }],
    keyDomain: [{ required: true, message: '请输入所属域', trigger: 'blur' }]
  }
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  const algorithm = queryParams.value.encrytName?.trim()
  const domain = queryParams.value.keyDomain?.trim()
  let rows = currentItems.value.map(item => ({
    algorithm: detailAlgorithm.value,
    domain: detailDomain.value,
    ...item
  }))

  if (algorithm) {
    rows = rows.filter(item => item.algorithm === algorithm)
  }
  if (domain) {
    rows = rows.filter(item => item.domain === domain)
  }

  paramList.value = rows
  total.value = rows.length
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  getList()
}

function handleAdd() {
  reset()
  open.value = true
}

function reset() {
  form.value = { encrytType: '无证书非对称加密', encrytName: 'SM2', keyDomain: 'A' }
  handleTypeChange('无证书非对称加密')
  proxy.resetForm('paramRef')
  form.value.encrytName = 'SM2'
}

function handleTypeChange(value) {
  if (value === '无证书非对称加密') {
    encrytNameOptions.value = [{ label: 'SM2', value: 'SM2' }, { label: 'SSCL', value: 'SSCL' }]
  } else {
    encrytNameOptions.value = []
  }
  if (!encrytNameOptions.value.find(item => item.value === form.value.encrytName)) {
    form.value.encrytName = encrytNameOptions.value[0]?.value || ''
  }
}

function submitForm() {
  proxy.$refs.paramRef.validate(valid => {
    if (!valid) {
      return
    }

    getComParam({
      encrytType: form.value.encrytType,
      encrytName: form.value.encrytName,
      keyDomain: form.value.keyDomain || 'A'
    }).then(response => {
      const items = buildParamItems(form.value.encrytName, response, form.value.keyDomain || 'A')
      currentItems.value = items
      detailAlgorithm.value = form.value.encrytName
      detailDomain.value = form.value.keyDomain || 'A'
      detailOpen.value = true
      open.value = false
      getList()
    })
  })
}

const detailTitle = computed(() => `${detailAlgorithm.value || ''}`)

function buildParamItems(algorithm, params, domain) {
  const common = [
    { key: 'N', label: algorithm === 'SSCL' ? 'SSCL 曲线阶 N' : 'SM2 曲线阶 N', value: params.N, description: '用于椭圆曲线运算的阶参数。' },
    { key: 'G', label: algorithm === 'SSCL' ? 'SSCL 生成元 G' : 'SM2 基点 G', value: params.G, description: '算法使用的基础椭圆曲线点。' },
    { key: 'PPub', label: algorithm === 'SSCL' ? 'SSCL 系统公钥 PPub' : 'SM2 系统公钥 PPub', value: params.PPub, description: 'KGC 对外公开的系统级公钥。' },
    { key: 'domain', label: algorithm === 'SSCL' ? '密钥所属域' : '参数所属域', value: domain, description: '当前参数适用的生成域。' }
  ]

  if (algorithm === 'SSCL') {
    return [
      ...common,
      { key: 'xIndex', label: 'SSCL 份额横坐标 xIndex', value: params.xIndex, description: 'SSCL 拉格朗日插值使用的公开横坐标集合。' },
      { key: 'yIndex', label: 'SSCL 份额纵坐标 yIndex', value: params.yIndex, description: '与 xIndex 配套的公开纵坐标集合。' }
    ]
  }

  return common
}

function copyParams() {
  const text = JSON.stringify({
    algorithm: detailAlgorithm.value,
    domain: detailDomain.value,
    items: currentItems.value
  }, null, 2)

  navigator.clipboard.writeText(text).then(() => {
    proxy.$modal.msgSuccess('参数已复制')
  })
}

reset()
getList()
</script>

<style scoped>
.param-value {
  word-break: break-all;
  font-family: monospace;
}

.param-desc {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}

.mb12 {
  margin-bottom: 12px;
}
</style>
