
<template>
    <div class="app-container">
        <div class="avatar-container">
            <div class="left-title">用户系统</div>
            <el-dropdown @command="handleCommand" class="right-menu-item hover-effect" trigger="click">
                <div class="avatar-wrapper">
                    <img :src="userStore.avatar" class="user-avatar" />
                    <el-icon><caret-bottom /></el-icon>
                </div>
                <template #dropdown>
                    <el-dropdown-menu>
                        <router-link to="/user/profile">
                            <el-dropdown-item>个人中心</el-dropdown-item>
                        </router-link>
                        <el-dropdown-item divided command="logout">
                            <span>退出登录</span>
                        </el-dropdown-item>
                    </el-dropdown-menu>
                </template>
            </el-dropdown>
        </div>
        <el-row :gutter="10" class="mb8">
            <el-col :span="1.5">
                <el-button
                    type="primary"
                    plain
                    icon="Plus"
                    @click="handleAdd"
                    style="padding: 6px 12px; margin-top: 15px;"
                >密钥生成</el-button>
            </el-col>
            <el-col :span="1.5">
                <el-button
                  type="success"
                  plain
                  icon="Edit"
                  :disabled="single"
                  @click="handleUpdate"
                  style="padding: 6px 12px; margin-top: 15px;"
                >密钥更新</el-button>
              </el-col>
              <el-col :span="1.5">
                <el-button
                  type="danger"
                  plain
                  icon="Delete"
                  :disabled="multiple"
                  @click="handleDelete"
                  style="padding: 6px 12px; margin-top: 15px;"
                >密钥回收</el-button>
              </el-col>
              <el-col :span="1.5">
                <el-button
                    type="info"
                    plain
                    icon="View"
                    @click="handleViewPublicKeys"
                    style="padding: 6px 12px; margin-top: 15px;"
                >查看公共密钥列表</el-button>
              </el-col>
              <el-col :span="1.5">
                <el-button
                    type="warning"
                    plain
                    icon="Setting"
                    @click="handleAutoUpdate"
                    style="padding: 6px 12px; margin-top: 15px;"
                >密钥自动更新</el-button>
              </el-col>
            </el-row>
        
        <el-tabs v-model="activeTab" class="user-tabs" style="margin-top: 20px;">
            <el-tab-pane label="我的密钥" name="mykeys">
                <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
                    <el-table-column type="selection" width="55" align="center" />
                    <el-table-column label="密钥ID" align="center" prop="keyId" />
                    <el-table-column label="用户ID" align="center" prop="userId" />
                    <el-table-column label="加密算法类型" align="center" prop="encrytType" />
                    <el-table-column label="加密算法名称" align="center" prop="encrytName" />
                    <el-table-column label="密钥名称" align="center" prop="keyName" />
                    <el-table-column label="密钥用途" align="center" prop="keyUse" />
                    <el-table-column label="创建时间" align="center" prop="creTime" />
                    <el-table-column label="更新时间" align="center" prop="updTime" />
                    <el-table-column label="密钥自动更新状态" align="center" prop="autoUpdate" />
                    </el-table>
                <pagination
                    v-show="total>0"
                    :total="total"
                    v-model:page="queryParams.pageNum"
                    v-model:limit="queryParams.pageSize"
                    @pagination="getList"
                />
            </el-tab-pane>

            <el-tab-pane label="公共密钥" name="publickeys" v-if="userStore.roleLevel <= 1">
                <el-alert v-if="showPublicKeysRollback" type="warning" :closable="false" style="margin-bottom: 15px;">
                    <template #default>
                        <el-button type="warning" size="small" icon="RefreshLeft" @click="handleRollbackFromTab">
                            操作完成，回退权限
                        </el-button>
                    </template>
                </el-alert>
                <el-form :inline="true" style="margin-bottom: 15px;">
                    <el-form-item label="用户名">
                        <el-input v-model="publicKeysQuery.userName" placeholder="请输入用户名" clearable style="width: 200px;" />
                    </el-form-item>
                    <el-form-item>
                        <el-button type="primary" icon="Search" @click="loadPublicKeys">搜索</el-button>
                    </el-form-item>
                </el-form>
                <el-table v-loading="publicKeysLoading" :data="publicKeysList">
                    <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
                    <el-table-column label="用户名" align="center" prop="userName" width="120" />
                    <el-table-column label="加密类型" align="center" prop="encrytType" width="120" />
                    <el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
                    <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
                    <el-table-column label="公钥值" align="center" prop="keyValue" :show-overflow-tooltip="true" min-width="200" />
                    <el-table-column label="创建时间" align="center" prop="creTime" width="160">
                        <template #default="scope">
                            <span>{{ parseTime(scope.row.creTime) }}</span>
                        </template>
                    </el-table-column>
                </el-table>
                <pagination
                    v-show="publicKeysTotal > 0"
                    :total="publicKeysTotal"
                    v-model:page="publicKeysQuery.pageNum"
                    v-model:limit="publicKeysQuery.pageSize"
                    @pagination="loadPublicKeys"
                />
            </el-tab-pane>

            <el-tab-pane label="密钥自动更新" name="autoupdate" v-if="userStore.roleLevel <= 0">
                <el-alert v-if="showAutoUpdateRollback" type="warning" :closable="false" style="margin-bottom: 15px;">
                    <template #default>
                        <el-button type="warning" size="small" icon="RefreshLeft" @click="handleRollbackFromTab">
                            操作完成，回退权限
                        </el-button>
                    </template>
                </el-alert>
                <el-form :inline="true" style="margin-bottom: 15px;">
                    <el-form-item label="密钥名称">
                        <el-input v-model="autoUpdateQuery.keyName" placeholder="请输入密钥名称" clearable style="width: 200px;" />
                    </el-form-item>
                    <el-form-item>
                        <el-button type="primary" icon="Search" @click="loadAutoUpdateKeys">搜索</el-button>
                    </el-form-item>
                </el-form>
                <el-table v-loading="autoUpdateLoading" :data="autoUpdateKeysList">
                    <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
                    <el-table-column label="用户名" align="center" prop="userName" width="120" />
                    <el-table-column label="加密类型" align="center" prop="encrytType" width="120" />
                    <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
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
                            <el-button link type="primary" icon="Edit" @click="toggleAutoUpdate(scope.row)">
                                切换状态
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
            </el-tab-pane>
        </el-tabs>
        <el-dialog :title="title" v-model="open" width="500px" append-to-body>
            <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="80px">
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
                    <el-input v-model="form.keyDomain" placeholder="请输入密钥所属域" />
                </el-form-item>
                </el-form>
            <template #footer>
                <div class="dialog-footer">
                    <el-button type="primary" @click="submitForm">确 定</el-button>
                    <el-button @click="cancel">取 消</el-button>
                </div>
            </template>
        </el-dialog>

        <el-dialog :title="permissionDialogTitle" v-model="permissionDialogOpen" width="500px" append-to-body>
            <el-form ref="permissionFormRef" :model="permissionForm" :rules="permissionRules" label-width="100px">
                <el-form-item label="申请理由" prop="requestReason">
                    <el-input
                        v-model="permissionForm.requestReason"
                        type="textarea"
                        :rows="4"
                        placeholder="请说明申请该权限的理由"
                    />
                </el-form-item>
                <el-alert
                    title="注意：此权限仅为临时权限，操作完成后将自动回退到普通用户等级。"
                    type="warning"
                    :closable="false"
                    style="margin-top: 10px;"
                />
            </el-form>
            <template #footer>
                <div class="dialog-footer">
                    <el-button type="primary" @click="submitPermissionRequest">提交申请</el-button>
                    <el-button @click="permissionDialogOpen = false">取 消</el-button>
                </div>
            </template>
        </el-dialog>

        <el-dialog title="操作完成" v-model="rollbackDialogOpen" width="400px" append-to-body>
            <p>您已完成操作，是否回退到普通用户权限？</p>
            <template #footer>
                <div class="dialog-footer">
                    <el-button type="primary" @click="handleRollback">回退权限</el-button>
                    <el-button @click="rollbackDialogOpen = false">稍后回退</el-button>
                </div>
            </template>
        </el-dialog>

        <!-- 权限提示对话框 -->
        <el-dialog 
            :title="permissionWarningTitle" 
            v-model="permissionWarningOpen" 
            width="450px" 
            append-to-body
        >
            <div class="permission-warning-content">
                <el-icon class="warning-icon" :size="60" color="#E6A23C">
                    <WarningFilled />
                </el-icon>
                <h3>权限不足</h3>
                <p>您当前没有访问"{{ permissionWarningFeature }}"功能的权限。</p>
                <el-divider />
                <div class="permission-info">
                    <p><strong>当前权限等级:</strong> {{ getRoleLevelText(userStore.roleLevel) }}</p>
                    <p><strong>所需权限等级:</strong> {{ getRoleLevelText(permissionWarningRequiredLevel) }}</p>
                </div>
                <el-alert
                    title="您可以申请临时权限来使用此功能，操作完成后请及时回退权限。"
                    type="info"
                    :closable="false"
                    show-icon
                    style="margin-top: 15px;"
                />
            </div>
            <template #footer>
                <div class="dialog-footer">
                    <el-button type="primary" @click="proceedToPermissionRequest" icon="Document">
                        申请权限
                    </el-button>
                    <el-button @click="permissionWarningOpen = false">取消</el-button>
                </div>
            </template>
        </el-dialog>
    </div>
</template>

<script setup name="Keymanage">
import {
  listKeymanage,
  getKeymanage,
  delKeymanage,
  addKeymanage,
  updateKeymanage,
  getComParam
} from "@/api/keymanage/keymanage";
import {
  submitPermissionRequest as apiSubmitPermissionRequest,
  rollbackPermission as apiRollbackPermission,
  listPermissionRequests
} from "@/api/permission/permission";
import useUserStore from '@/store/modules/user';
import useAppStore from '@/store/modules/app';
import useSettingsStore from '@/store/modules/settings';
import { getUserProfile } from "@/api/system/user";
import {SM2} from 'gm-crypto';
import {BigInteger} from "jsbn";
import {leftPad} from "@/views/utils.js";
import { WarningFilled } from '@element-plus/icons-vue';

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

// 权限相关
const permissionDialogOpen = ref(false);
const permissionDialogTitle = ref("");
const rollbackDialogOpen = ref(false);
const permissionForm = ref({
    requestReason: '',
    featureKey: null
});
const permissionRules = {
    requestReason: [
        { required: true, message: "请说明申请理由", trigger: "blur" },
        { min: 10, message: "申请理由不能少于10个字符", trigger: "blur" }
    ]
};
const approvedRequestIds = reactive({
  publickeys: null,
  autoupdate: null
});

// 权限提示对话框
const permissionWarningOpen = ref(false);
const permissionWarningTitle = ref('');
const permissionWarningFeature = ref('');
const permissionWarningRequiredLevel = ref(null);
const pendingFeatureKey = ref(null);

const permissionFeatureMap = {
  publickeys: {
    featureCode: 'PUBLIC_KEY_LIST',
    featureName: '查看公共密钥列表',
    systemCode: 'generate',
    requestLevel: 1
  },
  autoupdate: {
    featureCode: 'AUTO_UPDATE',
    featureName: '密钥自动更新',
    systemCode: 'lifecycle',
    requestLevel: 0
  }
};

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
        status: null,
        uA: null
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

const appStore = useAppStore();
const userStore = useUserStore();
const settingsStore = useSettingsStore();
// Tab state
const activeTab = ref('mykeys');
// Public Keys tab state
const publicKeysList = ref([]);
const publicKeysLoading = ref(false);
const publicKeysTotal = ref(0);
const publicKeysQuery = ref({
  pageNum: 1,
  pageSize: 10,
  userName: null
});
const showPublicKeysRollback = ref(false);
// Auto-Update tab state
const autoUpdateKeysList = ref([]);
const autoUpdateLoading = ref(false);
const autoUpdateTotal = ref(0);
const autoUpdateQuery = ref({
  pageNum: 1,
  pageSize: 10,
  keyName: null
});
const showAutoUpdateRollback = ref(false);

function getLoginPath() {
    const base = import.meta.env.BASE_URL || '/';
    return `${base.replace(/\/?$/, '/') }login`;
}

function handleCommand(command) {
    switch (command) {
        case "setLayout":
            setLayout();
            break;
        case "logout":
            logout();
            break;
        default:
            break;
    }
}

function logout() {
    proxy.$confirm('确定注销并退出系统吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(() => {
        userStore.logOut().then(() => {
            location.href = getLoginPath();
        })
    }).catch(() => { });
}

const emits = defineEmits(['setLayout'])
function setLayout() {
    emits('setLayout');
}

/** 查询密钥管理列表 */
function getList() {
    loading.value = true;
    return listKeymanage(queryParams.value).then(response => {
        // 过滤掉已回收的密钥（status='3'）
        keymanageList.value = response.rows.filter(key => key.status !== '3');
        total.value = keymanageList.value.length;
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
        userId: queryParams.value.userId,
        userName: queryParams.value.userName,
        encrytType: null,
        encrytName: null,
        keyName: null,
        keyUse: null,
        keyValue: null,
        creTime: null,
        updTime: null,
        autoUpdate: 'false',
        status: 'Valid',
        uA : 'null',
        keyDomain : 'A'
    };
    proxy.resetForm("keymanageRef");
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

//sm2生成服务端的部分公钥和私钥
const {publicKey, privateKey} = SM2.generateKeyPair();
/** 提交按钮 */
function submitForm() {
    proxy.$refs["keymanageRef"].validate(valid => {
        if (valid) {
            form.value.uA = publicKey;
            
            if (form.value.keyId != null) {
                console.log(form.value);
                updateKeymanage(form.value).then(response => {
                    proxy.$modal.msgSuccess("修改成功");
                    open.value = false;
                    getList();
                });
            } else {
                console.log(form.value);
                addKeymanage(form.value).then(async response => {
                    proxy.$modal.msgSuccess("新增成功");
                    open.value = false;
                    await getList();  // 等待列表刷新完成
                    console.log("列表已更新:", keymanageList.value);
                    await genDA();    // 然后再生成密钥
                    console.log("密钥生成完成:", keymanageList.value);
                });
            }
        }
    });
}
/** 生成用户的最终私钥 */
async function genDA() {
    const{xIndex,yIndex,PPub} = await genUA()
    console.log("genDA - xIndex:", xIndex)
    console.log("genDA - yIndex:", yIndex)
    console.log("genDA - PPub:", PPub)
    console.log("genDA - keymanageList长度:", keymanageList.value.length)
    
  keymanageList.value.forEach(item => {
    console.log("处理密钥:", item.keyId, "算法:", item.encrytName, "keyValue:", item.keyValue);
    
    if (item.encrytName == "SM2"){
    const n = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)
    const pratialKey = JSON.parse(item.keyValue).partialKey;
    const finalPublicKey = JSON.parse(item.keyValue).finalPublicKey;
    const num1 = new BigInteger(pratialKey ,16)
    const num2 = new BigInteger(privateKey ,16)
    const dA = (num1 + num2) % n;
    console.log("dA:" + dA.toString(16))
    item.PublicKey = finalPublicKey;
    console.log("Pk:" + finalPublicKey)
    if (1<dA<n-1){
      item.PrivateKey = leftPad(dA.toString(16),64);
    }else{
      proxy.$modal.msgSuccess("新增失败");
    }
    }else if (item.encrytName == "SSCL"){
        console.log("开始处理SSCL密钥:", item.keyId);
        
        // 检查必要参数
        if (!xIndex || !yIndex || !PPub) {
            console.error("SSCL密钥计算失败: 缺少公共参数 xIndex/yIndex/PPub");
            return;
        }
        
        try {
            const n = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)
            const keyValueObj = JSON.parse(item.keyValue);
            console.log("SSCL keyValue解析结果:", keyValueObj);
            
            const share = keyValueObj.SSCLKey;
            if (!share) {
                console.error("SSCL密钥计算失败: SSCLKey为空");
                return;
            }
            
            const prefix = share.slice(0, 2);
            const xHex = share.slice(2, 66);
            const yHex = share.slice(66, 130);
            console.log("SSCL share解析 - prefix:", prefix, "xHex:", xHex, "yHex:", yHex);
            
            const m = new BigInteger(xHex, 16);
            
            const secret = getsecret(xIndex,yIndex,xHex,yHex,n)
            console.log("SSCL secret:", secret.toString(16))
            const dA = secret.multiply(m).mod(n)
            const num1 = new BigInteger(privateKey ,16)
            //const sk = (num1 + dA) % n
            const sk = num1.add(dA).mod(n)
            console.log("sk:" + sk.toString(16))
            item.PrivateKey = leftPad(sk.toString(16),64)
            
            const PPubhex = PPub
            
            let dAHex = dA.toString(16); 
            dAHex = dAHex.padStart(64, '0').slice(-64);
            const resultHex = sm2PointMultiply(PPubhex, dAHex);
            item.DA = resultHex
            //console.log("DA:" + resultHex)

            let skHex = sk.toString(16); 
            skHex = skHex.padStart(64, '0').slice(-64);
            const PKHex = sm2PointMultiply(PPubhex, skHex);
            item.PublicKey = PKHex
            console.log("SSCL Pk:" + PKHex.slice(2,66))
            console.log("SSCL密钥计算成功")
        } catch (e) {
            console.error("SSCL密钥计算异常:", e);
        }
    }
    });
}
/** 生成用户部分公钥 */
function genUA() {
  //先保留，目前用不上，SM2参数公开可调库
  return getComParam(form.value).then(response =>{
    console.log("getComParam响应:", response);
    const G = response.G;
    const N = response.N;
    const PPub = response.PPub;
    // 添加空值检查，防止解析失败
    let xIndex = null;
    let yIndex = null;
    try {
      xIndex = response.xIndex ? JSON.parse(response.xIndex) : null;
      yIndex = response.yIndex ? JSON.parse(response.yIndex) : null;
    } catch (e) {
      console.error("解析xIndex/yIndex失败:", e);
    }
    
    if (!xIndex || !yIndex) {
      console.warn("SSCL公共参数xIndex或yIndex为空，可能影响密钥计算");
    }
    
    return {xIndex,yIndex,PPub}
  }).catch(error => {
    console.error("获取公共参数失败:", error);
    return {xIndex: null, yIndex: null, PPub: null};
  })
}
/** SSCL份额解密 */
function getsecret(xIndex,yIndex,xHex,yHex,n){
    // 确保x和y的数量匹配
    if (xIndex.length !== yIndex.length) {
        throw new Error("xIndex和yIndex数组长度必须相等");
    }
    
    // 将所有x坐标转换为BigInteger
    const xPoints = xIndex.map(x => new BigInteger(x, 16)); // 从16进制转换
    xPoints.push(new BigInteger(xHex, 16)); // 添加最后一个x坐标
    
    // 将所有y坐标转换为BigInteger
    const yPoints = yIndex.map(y => new BigInteger(y, 16)); // 从16进制转换
    yPoints.push(new BigInteger(yHex, 16)); // 添加最后一个y坐标
    
    const t = xIndex.length; // 多项式的次数
    let secret = new BigInteger("0"); // 初始化为0 
    // 拉格朗日插值法计算x=0处的值（秘密值）
    for (let i = 0; i <= t; i++) {
        let numerator = new BigInteger("1");
        let denominator = new BigInteger("1");
        for (let j = 0; j <= t; j++) {
            if (i !== j) {
                // 计算分子: (0 - x_j) 的乘积，即 (-x_j) 的乘积
                const xj = xPoints[j];
                numerator = numerator.multiply(xj.negate()).mod(n);
                
                // 计算分母: (x_i - x_j) 的乘积
                const xi = xPoints[i];
                const diff = xi.subtract(xj).mod(n);
                denominator = denominator.multiply(diff).mod(n);
            }
        }
        
        // 计算分母的模逆元
        const invDenominator = denominator.modInverse(n);
        if (invDenominator === null) {
            throw new Error("无法计算模逆元，可能是因为分母与模数不互质");
        }
        
        // 计算拉格朗日系数
        const li = numerator.multiply(invDenominator).mod(n);
        
        // 累加得到秘密值
        const term = yPoints[i].multiply(li).mod(n);
        secret = secret.add(term).mod(n);
    }
    
    // 确保结果为正数
    if (secret.negative) {
        secret = secret.add(n);
    }
    
    return secret;
}

import { ec as EC } from 'elliptic';
import BN from 'bn.js';
const sm2 = new EC('p256');
function sm2PointMultiply(hexPoint, hexScalar) {
    if (!hexPoint.startsWith('04')) {
        throw new Error('点格式错误，必须以04开头');
    }

    // 解析点
    const x = hexPoint.slice(2, 66);
    const y = hexPoint.slice(66, 130);
    const point = sm2.curve.point(new BN(x, 16), new BN(y, 16));

    // 标量转为 BN
    const scalar = new BN(hexScalar, 16);

    // 点乘
    const result = point.mul(scalar);

    // 返回未压缩十六进制格式
    const resultX = result.getX().toString('hex').padStart(64, '0');
    const resultY = result.getY().toString('hex').padStart(64, '0');
    return `04${resultX}${resultY}`;
}
// 手动实现十六进制字符串转Uint8Array
function hexToBytes(hex) {
  if (typeof hex !== 'string') {
    throw new Error('输入必须是十六进制字符串');
  }
  // 处理奇数长度的十六进制（补前导零）
  if (hex.length % 2 !== 0) {
    hex = '0' + hex;
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    const twoChars = hex.slice(i * 2, i * 2 + 2);
    bytes[i] = parseInt(twoChars, 16);
  }
  return bytes;
}

// 手动实现Uint8Array转十六进制字符串
function bytesToHex(bytes) {
  if (!(bytes instanceof Uint8Array)) {
    throw new Error('输入必须是Uint8Array');
  }
  const hexChars = [];
  for (const byte of bytes) {
    // 确保每个字节转换为两位十六进制（补前导零）
    hexChars.push(byte.toString(16).padStart(2, '0'));
  }
  return hexChars.join('');
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

// function getUser() {
//   getUserProfile().then(response => {
//     const userId = response.data.userId;
//     console.log(777777, response.data)
//     console.log(888888, userId)
//   });
// };

// getUser();

// if (!userId) {
//     console.error('未获取到用户ID，尝试从其他方式获取');
//     // 这里可以添加更多获取userId的逻辑，例如从其他store中获取
// } else {
//     queryParams.value.userId = userId;
//     getList();
// }

let userId;
let userName;

function getUser() {
    return getUserProfile().then(response => {
        userId = response.data.userId;
        userName = response.data.userName;
        return {userId,userName};
    });
}

getUser().then(() => {
    if (!userId || !userName) {
        console.error('未获取到用户ID或用户名，尝试从其他方式获取');
        // 这里可以添加更多获取userId的逻辑，例如从其他store中获取
    } else {
        queryParams.value.userId = userId;
        queryParams.value.userName = userName;
        getList();
    }
}).catch(error => {
    console.error('获取用户信息时出错:', error);
});

// ========== 权限相关函数 ==========

/** 查看公共密钥列表（需要 role_level = 1） */
function handleViewPublicKeys() {
    if (userStore.roleLevel > 1) {
        showPermissionWarning('publickeys');
    } else {
        activeTab.value = 'publickeys';
        proxy.$message.success('已切换到公共密钥视图');
    }
}

/** 密钥自动更新（需要 role_level = 0） */
function handleAutoUpdate() {
    if (userStore.roleLevel > 0) {
        showPermissionWarning('autoupdate');
    } else {
        activeTab.value = 'autoupdate';
        proxy.$message.success('已切换到密钥自动更新视图');
    }
}

/** 显示权限提示对话框 */
function showPermissionWarning(featureKey) {
    const feature = permissionFeatureMap[featureKey];
    if (!feature) {
      return;
    }
    permissionWarningTitle.value = '权限不足提示';
    permissionWarningFeature.value = feature.featureName;
    permissionWarningRequiredLevel.value = feature.requestLevel;
    pendingFeatureKey.value = featureKey;
    permissionWarningOpen.value = true;
}

/** 从提示页面进入权限申请 */
function proceedToPermissionRequest() {
    permissionWarningOpen.value = false;
    showPermissionDialog(pendingFeatureKey.value);
}

/** 显示权限申请对话框 */
function showPermissionDialog(featureKey) {
    const feature = permissionFeatureMap[featureKey];
    if (!feature) {
      return;
    }
    permissionForm.value = {
        requestReason: '',
        featureKey
    };
    permissionDialogTitle.value = `申请\"${feature.featureName}\"权限`;
    permissionDialogOpen.value = true;
}

/** 获取权限等级文本 */
function getRoleLevelText(level) {
    const levelMap = {
        0: '管理员',
        1: '中级用户',
        2: '普通用户'
    };
    return levelMap[level] || '未知';
}

/** 提交权限申请 */
function submitPermissionRequest() {
    proxy.$refs["permissionFormRef"].validate(valid => {
        if (valid) {
            const feature = permissionFeatureMap[permissionForm.value.featureKey];
            if (!feature) {
                proxy.$modal.msgError("未识别的申请功能");
                return;
            }
            const requestData = {
                userId: userStore.id,
                userName: userStore.name,
                originalLevel: userStore.roleLevel,
                requestLevel: feature.requestLevel,
                requestReason: `申请"${feature.featureName}"功能权限：${permissionForm.value.requestReason}`,
                isTemp: 1,
                featureCode: feature.featureCode,
                featureName: feature.featureName,
                systemCode: feature.systemCode
            };

            apiSubmitPermissionRequest(requestData).then(response => {
                proxy.$modal.msgSuccess("权限申请已提交，请等待管理员审批");
                permissionDialogOpen.value = false;
                checkApprovalStatus(permissionForm.value.featureKey);
            }).catch(error => {
                proxy.$modal.msgError("提交申请失败：" + error.message);
            });
        }
    });
}

/** 检查申请审批状态（轮询） */
function checkApprovalStatus(featureKey) {
    const checkInterval = setInterval(() => {
        loadApprovedRequest(featureKey).then(approvedRequest => {
            if (approvedRequest) {
                approvedRequestIds[featureKey] = approvedRequest.requestId;
                userStore.getInfo().then(() => {
                    clearInterval(checkInterval);
                });
            }
        });
    }, 5000);

    // 5分钟后停止轮询
    setTimeout(() => {
        clearInterval(checkInterval);
    }, 300000);
}

/** 回退权限到原始等级 */
function handleRollback() {
    const requestId = approvedRequestIds[activeTab.value];
    if(!requestId) {
        proxy.$modal.msgWarning("没有可回退的权限申请");
        return;
    }

    apiRollbackPermission(requestId).then(response => {
        proxy.$modal.msgSuccess("权限已回退到普通用户等级");
        rollbackDialogOpen.value = false;
        approvedRequestIds[activeTab.value] = null;

        // 刷新用户信息
        userStore.getInfo();
    }).catch(error => {
        proxy.$modal.msgError("回退失败：" + error.message);
    });
}
/** Load public keys */
function loadPublicKeys() {
  publicKeysLoading.value = true;
  listKeymanage(publicKeysQuery.value).then(response => {
    publicKeysList.value = response.rows;
    publicKeysTotal.value = response.total;
    publicKeysLoading.value = false;
  });
}
/** Load auto-update keys */
function loadAutoUpdateKeys() {
  autoUpdateLoading.value = true;
  listKeymanage(autoUpdateQuery.value).then(response => {
    autoUpdateKeysList.value = response.rows;
    autoUpdateTotal.value = response.total;
    autoUpdateLoading.value = false;
  });
}
/** Toggle auto-update status */
function toggleAutoUpdate(row) {
  const newStatus = row.autoUpdate === 1 ? 0 : 1;
  const statusText = newStatus === 1 ? '启用' : '禁用';

  proxy.$modal.confirm(`确认${statusText}密钥"${row.keyName}"的自动更新功能？`).then(() => {
    updateKeymanage({
      keyId: row.keyId,
      autoUpdate: newStatus
    }).then(() => {
      proxy.$modal.msgSuccess(`已${statusText}自动更新`);
      loadAutoUpdateKeys();
    });
  }).catch(() => {});
}
/** Handle rollback from tab */
function handleRollbackFromTab() {
  const featureKey = activeTab.value;
  const requestId = approvedRequestIds[featureKey];
  if (!requestId) {
    proxy.$modal.msgWarning("没有可回退的权限申请");
    return;
  }

  proxy.$modal.confirm('确认回退到普通用户权限？').then(() => {
    apiRollbackPermission(requestId).then(() => {
      proxy.$modal.msgSuccess("权限已回退成功！");
      showPublicKeysRollback.value = false;
      showAutoUpdateRollback.value = false;
      approvedRequestIds.publickeys = null;
      approvedRequestIds.autoupdate = null;

      userStore.getInfo().then(() => {
        setTimeout(() => {
          activeTab.value = 'mykeys';
          window.location.reload();
        }, 1000);
      });
    });
  }).catch(() => {});
}
/** Check rollback status for tab */
function checkRollbackStatus(tab) {
  if (userStore.roleLevel === 0 || userStore.roleLevel === 1) {
    loadApprovedRequest(tab).then(request => {
      approvedRequestIds[tab] = request?.requestId || null;
      if (tab === 'publickeys') {
        showPublicKeysRollback.value = Boolean(request);
      } else if (tab === 'autoupdate') {
        showAutoUpdateRollback.value = Boolean(request);
      }
    });
  }
}

function loadApprovedRequest(featureKey) {
  const feature = permissionFeatureMap[featureKey];
  if (!feature || !userStore.id) {
    return Promise.resolve(null);
  }

  return listPermissionRequests({
    userId: userStore.id,
    status: '1',
    requestLevel: feature.requestLevel
  }).then(response => {
    const rows = Array.isArray(response.rows) ? response.rows : [];
    const matched = rows
      .filter(item => isApprovedTempRequest(item, feature))
      .sort(comparePermissionRequest);
    return matched[0] || null;
  });
}

function isApprovedTempRequest(item, feature) {
  if (!item || String(item.status) !== '1') {
    return false;
  }

  const isTemp = item.isTemp === 1 || item.isTemp === '1' || item.isTemp === true;
  if (!isTemp) {
    return false;
  }

  if (item.featureCode) {
    return item.featureCode === feature.featureCode;
  }

  if (item.systemCode && item.systemCode !== feature.systemCode) {
    return false;
  }

  const sameLevel = Number(item.requestLevel) === feature.requestLevel;
  const sameFeature = typeof item.requestReason === 'string' && item.requestReason.includes(feature.featureName);
  return sameLevel && sameFeature;
}

function comparePermissionRequest(a, b) {
  return getPermissionRequestTime(b) - getPermissionRequestTime(a);
}

function getPermissionRequestTime(item) {
  const time = item?.approveTime || item?.requestTime;
  const parsed = time ? new Date(time).getTime() : NaN;
  if (!Number.isNaN(parsed)) {
    return parsed;
  }
  return Number(item?.requestId) || 0;
}
// Watch tab changes
watch(activeTab, (newTab) => {
  if (newTab === 'publickeys') {
    loadPublicKeys();
    checkRollbackStatus('publickeys');
  } else if (newTab === 'autoupdate') {
    loadAutoUpdateKeys();
    checkRollbackStatus('autoupdate');
  }
});
</script>

<style scoped>
 ::v-deep .el-dropdown {
    position:absolute;
    right:0;
 }
.avatar-container {
    position: relative;
    display: flex;
    align-items: center;
    /* margin-left: 10px; 调整与notices的间距 */
}
.avatar-container .left-title {
    font-size:24px;
    font-weight: 600;
}
.avatar-container .avatar-wrapper {
    margin-top: 5px;
    position: relative;
}
.avatar-container .avatar-wrapper .user-avatar {
    cursor: pointer;
    width: 40px;
    height: 40px;
    border-radius: 10px;
}
.avatar-container .avatar-wrapper i {
    cursor: pointer;
    position: absolute;
    right: -20px;
    top: 25px;
    font-size: 12px;
}

.permission-warning-content {
  text-align: center;
  padding: 20px 10px;
}

.permission-warning-content .warning-icon {
  margin-bottom: 20px;
}

.permission-warning-content h3 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 10px;
  color: #303133;
}

.permission-warning-content > p {
  font-size: 15px;
  color: #606266;
  margin-bottom: 15px;
}

.permission-info {
  background-color: #f5f7fa;
  border-radius: 8px;
  padding: 15px;
  text-align: left;
  margin-top: 10px;
}

.permission-info p {
  margin: 8px 0;
  font-size: 14px;
  color: #606266;
}

.permission-info strong {
  color: #303133;
  font-weight: 600;
}
</style>
