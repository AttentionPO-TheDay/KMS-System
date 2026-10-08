<template>
  <div class="login">
    <el-form ref="loginRef" :model="loginForm" :rules="loginRules" class="login-form">
      <h3 class="title">密钥管理系统</h3>

      <!--
        身份选择（单一登录入口）。
        文档 §2 原本设想 /admin/login 与 /node/login 两个入口；这里改为
        **一个入口 + 先选身份**，对使用者更短，且底层仍是同一套
        Token / Redis Session（§2 要求"底层复用现有认证基础设施"）。

        ⚠️ 这只是**声明意图**，不是权限判断。
           真正的身份来自服务端 getInfo 返回的 principalType/roleLevel，
           由路由守卫做严格校验（见 permission.js）。选错会被拒绝登录，
           而不是被"信任"这个下拉框 —— 前端声明永远不能当作授权依据。
      -->
      <el-radio-group v-model="loginForm.declaredPrincipal" class="principal-switch" size="large">
        <el-radio-button label="ADMIN">管理员</el-radio-button>
        <el-radio-button label="NODE">节点</el-radio-button>
      </el-radio-group>

      <p class="principal-hint">{{ principalHint }}</p>

      <!--
        节点身份：两种进入方式。
          上：**已激活节点** —— 本机存有该节点的设备私钥，点一下就走挑战-应答，
              不输入任何东西（按设计的"看似只输入节点名称"，真实依据是本地私钥）。
          下：**首次激活** —— 输入节点名 + 管理员给的一次性凭证。

        ⚠️ 这条列表读的是**本机 IndexedDB**（NodeKeyStore），不是服务端。
           所以它天然回答了"这个浏览器托管了哪些节点"——同一浏览器可以有多个，
           这正是文档 §4 的设计（一个浏览器 ≠ 一个节点，而是一个可托管多身份的环境）。
      -->
      <template v-if="isNodeMode">
        <div v-if="hasActivated" class="activated-block">
          <div class="activated-title">已激活节点</div>
          <div class="activated-list">
            <button
              v-for="id in activatedNodes"
              :key="id"
              type="button"
              class="activated-item"
              :disabled="anyNodeBusy"
              @click="handleQuickLogin(id)"
            >
              <span class="activated-main">
                <span class="activated-name">{{ id }}</span>
                <!-- 绑定文件里的最近登录时间。没有绑定记录（本功能上线前激活的
                     存量浏览器）就什么都不显示，不编一个时间出来。 -->
                <span v-if="bindingOf(id)?.lastLoginAt" class="activated-meta">
                  上次登录 {{ formatBindingTime(bindingOf(id).lastLoginAt) }}
                </span>
              </span>
              <span class="activated-action">{{ busyNode === id ? '登录中…' : '点击登录' }}</span>
            </button>
          </div>
          <!--
            这台设备已经有可免密登录的节点时，**默认把表单收起来**。

            理由：节点侧登进来几乎总是"就登这一个节点"，而表单那两个框
            （节点名 + 一次性凭证）看着像"每次都得填"，很容易让人以为
            免密登录失效了、又一次次去敲凭证。收起来之后这一页的语义是
            「点一下就进」，表单变成**按需展开**的次要路径。

            ⚠️ 按钮只在"有已激活节点**且**表单当前是收起状态"时出现 ——
               展开着还留一个开关，它就变成了"点了没反应"的装饰。
          -->
          <el-button
            v-if="!showActivateForm"
            class="switch-node-btn"
            plain
            :disabled="anyNodeBusy"
            @click="openActivateForm"
          >
            登录其它节点
          </el-button>
        </div>
        <div v-else class="activated-empty">
          本机还没有已激活的节点。用管理员给的激活凭证在下方完成首次激活。
        </div>
      </template>

      <el-form-item v-if="!isNodeMode" prop="username">
        <el-input
          v-model="loginForm.username"
          type="text"
          size="large"
          auto-complete="off"
          placeholder="账号"
        >
          <template #prefix><svg-icon icon-class="user" class="el-input__icon input-icon" /></template>
        </el-input>
      </el-form-item>

      <!-- 节点首次激活：节点名 + 一次性凭证，没有口令。
           ⚠️ `nodeFormVisible`：已有可免密登录的节点时这张表单**默认收起**
              （见上方「登录其它节点」按钮的说明）；下面那句提示同理。 -->
      <template v-else-if="nodeFormVisible">
        <div v-if="hasActivated" class="form-context">
          新节点登录需用管理员签发的激活凭证；完成激活后自动切到它，
          本机不再保留 <span class="mono">{{ activatedNodes.join('、') }}</span> 的登录信息。
          <el-button link type="primary" size="small" @click="closeActivateForm">收起</el-button>
        </div>
        <el-form-item prop="nodeId">
          <el-input
            v-model="loginForm.nodeId"
            type="text"
            size="large"
            auto-complete="off"
            placeholder="节点名称（如 Node-001）"
          >
            <template #prefix><svg-icon icon-class="user" class="el-input__icon input-icon" /></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="activationCode">
          <!--
            激活凭证按**密码**的方式展示（不显示明文）。

            ⚠️ 它不会长期留在输入框里：激活成功即进入系统；失败（凭证错、
               节点名错）时服务端不消耗凭证，用户改一下节点名就能重试 ——
               所以清空输入框并不是必须的，反而不清空更省事。
               但**明文常驻屏幕**这件事本身要避免：它是一次性凭证、
               高熵随机串，防的是"被旁人/被截屏看走"。

            `show-password` 给眼睛图标：需要核对时点一下即可见，
            不是"藏起来不让看"。整串字很长（43 字符）塞在 400px 的卡片里
            本来也读不全，默认可见的实用价值很低。
          -->
          <el-input
            v-model="loginForm.activationCode"
            type="password"
            show-password
            size="large"
            auto-complete="off"
            placeholder="激活凭证（管理员签发，仅显示一次）"
            @keyup.enter="handleNodeActivate"
          >
            <template #prefix><svg-icon icon-class="password" class="el-input__icon input-icon" /></template>
          </el-input>
        </el-form-item>
      </template>

      <el-form-item v-if="!isNodeMode" prop="password">
        <el-input
          v-model="loginForm.password"
          type="password"
          size="large"
          auto-complete="off"
          placeholder="密码"
          @keyup.enter="handleLogin"
        >
          <template #prefix><svg-icon icon-class="password" class="el-input__icon input-icon" /></template>
        </el-input>
      </el-form-item>
      <el-form-item v-if="!isNodeMode && captchaEnabled" prop="code">
        <el-input
          v-model="loginForm.code"
          size="large"
          auto-complete="off"
          placeholder="验证码"
          style="width: 63%"
          @keyup.enter="handleLogin"
        >
          <template #prefix><svg-icon icon-class="validCode" class="el-input__icon input-icon" /></template>
        </el-input>
        <div class="login-code">
          <img :src="codeUrl" @click="getCode" class="login-code-img"/>
        </div>
      </el-form-item>

      <el-checkbox v-if="!isNodeMode" v-model="loginForm.rememberMe" style="margin:0px 0px 25px 0px;">记住密码</el-checkbox>

      <el-form-item style="width:100%;">
        <el-button
          v-if="!isNodeMode"
          :loading="loading"
          size="large"
          type="primary"
          style="width:100%;"
          @click.prevent="handleLogin"
        >
          <span v-if="!loading">登 录</span>
          <span v-else>登 录 中...</span>
        </el-button>
        <el-button
          v-else-if="nodeFormVisible"
          :loading="loading"
          size="large"
          type="primary"
          style="width:100%;"
          @click.prevent="handleNodeActivate"
        >
          <span v-if="!loading">激活并登录</span>
          <span v-else>激 活 中...</span>
        </el-button>
      </el-form-item>
    </el-form>
    <!--  底部  -->
    <!-- <div class="el-login-footer">
      <span>Copyright © 2018-2024 ruoyi.vip All Rights Reserved.</span>
    </div> -->
  </div>
</template>

<script setup>
import { getCodeImg } from "@/api/login";
import Cookies from "js-cookie";
import { ElMessage, ElMessageBox } from "element-plus";
import { encrypt, decrypt } from "@/utils/jsencrypt";
import { listActivatedNodes, removeDeviceKey } from '@/utils/crypto/device-credential';
import { clearOtherBindings, listBindings, removeBinding } from '@/utils/crypto/node-binding';
import { probeNodesExist } from '@/api/pqkds/node-self';
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const route = useRoute();
const router = useRouter();
const { proxy } = getCurrentInstance();

const loginForm = ref({
  // 身份声明：ADMIN / NODE。仅表示"我想以哪种身份进入"，
  // 服务端返回的真实身份与之不符时会被守卫拒绝（见 permission.js）。
  declaredPrincipal: 'ADMIN',
  username: "",
  password: "",
  rememberMe: false,
  code: "",
  uuid: "",
  // 节点首次激活用（与口令互斥）
  nodeId: "",
  activationCode: ""
});

const isNodeMode = computed(() => loginForm.value.declaredPrincipal === 'NODE')

const principalHint = computed(() =>
  isNodeMode.value
    ? '用管理员签发的激活凭证完成首次激活，之后本机可直接点击已激活节点登录。'
    : '平台管理员，可创建节点、监管密钥生命周期与查看审计。'
);

const loginRules = {
  username: [{ required: true, trigger: "blur", message: "请输入您的账号" }],
  password: [{ required: true, trigger: "blur", message: "请输入您的密码" }],
  code: [{ required: true, trigger: "change", message: "请输入验证码" }]
};

/**
 * 本机已激活的节点（读 IndexedDB，不是服务端）。
 *
 * ⚠️ 只在切到节点身份时才读 —— 管理员模式下没必要碰本机密钥库，
 *    而且某些浏览器/隐私模式读 IndexedDB 会抛异常，能少碰就少碰。
 */
const activatedNodes = ref([])
/**
 * 本机**确实还能登录**的节点（= `activatedNodes` 非空）。
 * 它就是"默认展示免密登录、收起表单"的判据 —— 用一个具名 computed 而不是
 * 到处写 `.length`，因为这条件将来若变（比如要求绑定文件也在），只改一处。
 */
const hasActivated = computed(() => activatedNodes.value.length > 0)
/**
 * 节点侧「新节点登录」表单是否展开。
 *
 * 默认收起（有已激活节点时）—— 见模板里「登录其它节点」按钮的说明。
 * ⚠️ 每次切回「节点」页签都重置为 false：用户上次展开了表单、这次切过来
 *    是因为想点免密登录，还留着一张开着的表单就把默认路径又盖住了。
 */
const showActivateForm = ref(false)
/** 表单实际可见 = 没有可免密登录的节点（必须填）**或**用户主动展开了它。 */
const nodeFormVisible = computed(() => !hasActivated.value || showActivateForm.value)

function openActivateForm() {
  showActivateForm.value = true
}

function closeActivateForm() {
  showActivateForm.value = false
}
/**
 * 本机各节点的**绑定文件**，按节点编号索引（`node-binding.js`）。
 *
 * 登录成功后本机会写下绑定文件（节点名、设备指纹、首次/最近登录时间）。
 * 这张表只用来在列表里显示"上次登录 …" —— 没有绑定记录的节点（本功能上线前
 * 就激活过的存量浏览器）照样列出、照样能登录，只是不显示这一行。
 */
const bindings = ref({})
const bindingOf = (nodeId) => bindings.value[nodeId] || null

function formatBindingTime(value) {
  if (!value) return ''
  const d = new Date(String(value))
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 正在免输入登录的节点 id；空串表示没有在忙。
 *
 * ⚠️ 模板里**不要**直接把它绑给 `:disabled` —— 用 `anyNodeBusy` 那个布尔。
 *    绑字符串会踩到 HTML 布尔属性的坑：空串在 `disabled` 这类属性上
 *    并不总是等价于 false，实测（2026-09-30）按钮一直是禁用态，
 *    而"点不动"被误读成"点击没反应"，查了半天。
 */
const busyNode = ref('')
const anyNodeBusy = computed(() => busyNode.value !== '')
/**
 * 正在弹「切换绑定节点」确认框。
 *
 * ⚠️ 防的是**连点叠框**：确认框弹出时登录还没开始（`busyNode` 还是空），
 *    第二次点击会走到同一分支、再弹一个 —— 用户看到两个一样的框，
 *    点掉一个另一个还在，而它们各自持有自己那份"当前绑定"快照。
 */
const switchingNode = ref(false)

async function refreshActivatedNodes() {
  if (!isNodeMode.value) {
    activatedNodes.value = []
    bindings.value = {}
    return
  }
  activatedNodes.value = await listActivatedNodes()
  await reconcileLocalNodes()
  // ⚠️ 只保留**本机确实还能登录**的那些节点的绑定：绑定文件可能比设备凭据
  //    活得久（本机凭据被单独清掉、或用户手工删过 deviceKeys 记录）。
  //    不过滤的话，"当前绑定"会指向一个列表里根本不存在、也点不进去的节点，
  //    而换节点确认框会拿它当"当前绑定"念出来 —— 用户看得见却找不到它。
  //    （这些悬空记录仍留在盘上，换节点时 `clearOtherBindings` 会一并清掉。）
  const present = new Set(activatedNodes.value)
  const all = await listBindings()
  bindings.value = Object.fromEntries(
    all.filter((b) => present.has(b.nodeId)).map((b) => [b.nodeId, b])
  )
}

/**
 * 用**服务端事实**校对本机的"已激活节点"列表，清掉服务端已经没有的。
 *
 * 为什么需要：数据库被重置 / 管理员删了节点之后，浏览器里仍留着那个节点的
 * 设备凭据与绑定文件 —— 它出现在「已激活节点」里，点下去只会得到一句
 * "节点不存在"，而用户看不出它已经作废，也删不掉（界面上没有删除入口）。
 *
 * ⚠️ 探测**失败时不清理**（`probeNodesExist` 返回 null）。这是刻意的：
 *    网络抖动、后端还没升级到带这条路由的版本，都会让"存在性"无从判断 ——
 *    此时若按"查不到就删"处理，会把用户**唯一那条能用的登录记录**删掉，
 *    而那是不可逆的（私钥不可导出，删了就只剩重新激活一条路）。
 *    宁可留着一条点不动的条目。
 *
 * ⚠️ 只清本机，**不动服务端**：服务端没这个节点是它的现状，不需要我们去"修正"。
 */
async function reconcileLocalNodes() {
  const ids = activatedNodes.value
  if (!ids.length) {
    return
  }
  const exists = await probeNodesExist(ids)
  if (!exists) {
    return // 问不出来 → 什么都不做（见上）
  }
  const stale = ids.filter((id) => exists[id] === false)
  if (!stale.length) {
    return
  }
  // ⚠️ 逐个删，**不要**图省事调 `clearOtherBindings('')` —— 那个函数的语义是
  //    "保留 keepNodeId、清掉其余全部"，传空串等于"全清"，会把**能用的那条**
  //    也一起删掉（本机私钥不可导出，删了就只剩重新激活）。
  for (const id of stale) {
    await removeDeviceKey(id)
    await removeBinding(id)
  }
  activatedNodes.value = await listActivatedNodes()
  console.info(`[login] 已清理 ${stale.length} 个服务端已不存在的本地节点记录：${stale.join('、')}`)
}

watch(isNodeMode, (nodeMode) => {
  if (nodeMode) {
    // 每次切到「节点」都回到"先看免密登录"的默认形态（见 showActivateForm 说明）。
    showActivateForm.value = false
    refreshActivatedNodes()
  } else {
    activatedNodes.value = []
  }
}, { immediate: true })

const codeUrl = ref("");
const loading = ref(false);
// 验证码开关
const captchaEnabled = ref(true);
const redirect = ref(undefined);

watch(route, (newRoute) => {
    redirect.value = newRoute.query && newRoute.query.redirect;
}, { immediate: true });

function handleLogin() {
  proxy.$refs.loginRef.validate(valid => {
    if (valid) {
      loading.value = true;
      // 勾选了需要记住密码设置在 cookie 中设置记住用户名和密码
      if (loginForm.value.rememberMe) {
        Cookies.set("username", loginForm.value.username, { expires: 30 });
        Cookies.set("password", encrypt(loginForm.value.password), { expires: 30 });
        Cookies.set("rememberMe", loginForm.value.rememberMe, { expires: 30 });
      } else {
        // 否则移除
        Cookies.remove("username");
        Cookies.remove("password");
        Cookies.remove("rememberMe");
      }
      // 调用action的登录方法
      userStore.login(loginForm.value).then((token) => {
        // 只有登录 action 返回有效 token 才允许进入后续路由。
        // 失败登录由 request.js 拒绝并进入 catch，绝不能导航到受保护页面。
        if (!token) {
          loading.value = false;
          return;
        }
        const query = route.query;
        const otherQueryParams = Object.keys(query).reduce((acc, cur) => {
          if (cur !== "redirect") {
            acc[cur] = query[cur];
          }
          return acc;
        }, {});
        // 跳根路径，由路由守卫按**服务端返回的真实身份**决定落到管理端还是
        // 节点端，并校验与上面的声明是否一致。
        // 这里刻意不自己判身份跳转 —— 前端只有声明，判断权在守卫。
        router.push({ path: redirect.value || "/", query: otherQueryParams });
      }).catch((err) => {
        loading.value = false;
        // 身份不匹配：服务端身份是权威，本地会话已被守卫清掉，如实告知。
        // 这条不是接口错误，不要落进"重新获取验证码"以外的通用处理就当失败。
        ElMessage.error(err?.message || '登录失败');
        // 重新获取验证码
        if (captchaEnabled.value) {
          getCode();
        }
      });
    }
  });
}

/**
 * 节点首次激活：节点名 + 一次性凭证 → 本机生成设备密钥 → 换令牌。
 *
 * ⚠️ 这条路径**没有口令**。节点账号在服务端的口令是随机且不披露的
 *    （见 node_account_service），所以"输错凭证"就是唯一的失败方式，
 *    不存在"凭证对但口令错"这种中间态。
 */
async function handleNodeActivate() {
  // 回车/连点会重复进来：激活是**消耗凭证**的动作，第二次请求只会拿到
  // "凭证已用"的报错，把一次成功的激活显示成失败。这里与「激活并登录」
  // 按钮的 :loading 是同一道闸（按钮上的 loading 只在请求发出后生效，
  // 而确认框那一段是异步的）。
  if (loading.value || switchingNode.value) {
    return
  }
  const nodeId = String(loginForm.value.nodeId || '').trim()
  const code = String(loginForm.value.activationCode || '').trim()
  if (!nodeId) {
    ElMessage.warning('请输入节点名称')
    return
  }
  if (!code) {
    ElMessage.warning('请输入管理员签发的激活凭证')
    return
  }

  loading.value = true
  // 激活也是"进入某个节点"的一种。本机已有别的绑定时，同样要问一次 ——
  // 直接激活会把新节点写进绑定，而旧那份悄悄留在本机（两个身份并存）。
  const pending = currentBindingEntry()
  if (pending && pending.nodeId !== nodeId && !(await confirmNodeSwitch(pending, nodeId))) {
    loading.value = false
    return
  }
  userStore.activateNodeWithCode({ nodeId, code })
    .then(async () => {
      // 激活成功：本机现在有该节点的设备凭据，绑定文件也已写下
      // （`userStore.activateNodeWithCode` 里落库）。
      // 之后所有登录都走挑战-应答，不再需要凭证。
      loading.value = false
      ElMessage.success('激活成功，正在进入…')
      if (pending && pending.nodeId !== nodeId) {
        await purgeOtherBindings(nodeId)
      }
      enterAfterNodeLogin()
    })
    .catch((error) => {
      loading.value = false
      ElMessage.error(error?.message || '激活失败')
    })
}

/** 本机当前绑定（最近登录的那一份）；没有绑定文件时返回 null。 */
function currentBindingEntry() {
  return Object.values(bindings.value)
    .sort((a, b) => String(b.lastLoginAt || '').localeCompare(String(a.lastLoginAt || '')))[0] || null
}

/** 已激活节点：点一下就走挑战-应答，不输入任何东西 */
async function handleQuickLogin(nodeId) {
  // `switchingNode` 一起挡：确认框弹出的那一瞬间登录还没开始
  // （`busyNode` 仍是空），连点会叠出第二个框。
  if (anyNodeBusy.value || switchingNode.value) {
    return
  }
  // 先判定"这是不是切换节点"：本机有绑定文件、且绑的不是这个节点。
  // 确认框要在**发起登录之前**弹 —— 登录本身会把绑定文件刷成新节点，
  // 那时候再问"要不要清掉旧的"已经晚了（"当前绑定"已经不是原来那个了）。
  const pending = currentBindingEntry()
  if (pending && pending.nodeId !== nodeId && !(await confirmNodeSwitch(pending, nodeId))) {
    return
  }

  busyNode.value = nodeId
  userStore.loginAsActivatedNode(nodeId)
    .then(async () => {
      busyNode.value = ''
      // 登录成功即落绑定文件（刷新最近登录时间；首登时间保留原值）——
      // 这一步在 store 的登录动作里完成。
      if (pending && pending.nodeId !== nodeId) {
        await purgeOtherBindings(nodeId)
      }
      enterAfterNodeLogin()
    })
    .catch((error) => {
      busyNode.value = ''
      ElMessage.error(error?.message || '登录失败')
      // 失败可能是本机凭据与服务端登记的不一致（换过设备/清过数据）。
      // 刷新一次列表，让"其实用不了"的节点不再显示成可点。
      refreshActivatedNodes()
    })
}

/**
 * 「换节点」确认框。返回 true = 用户同意继续（并同意清除旧绑定）。
 *
 * 文案的落点
 * ----------
 *   1. 这台浏览器**同时只服务一个节点** —— 登录新节点会清掉旧的登录身份；
 *   2. 清掉之后旧节点要在这台浏览器上再登录，**只能由管理员重签激活凭证**
 *      （设备公钥还登记在服务端，本机私钥没了就签不出挑战）；
 *   3. 用户随时可以取消，取消即本次登录作废（不产生任何副作用）。
 *
 * 不复述"文件"这个词：界面语言是"绑定"，真正被删掉的是本机那份设备凭据 +
 * 绑定记录。用户要理解的是后果（要重签凭证），不是存储实现。
 */
async function confirmNodeSwitch(fromBinding, toNodeId) {
  if (switchingNode.value) {
    return false
  }
  switchingNode.value = true
  const from = fromBinding?.nodeId || ''
  const fromName = fromBinding?.nodeName ? `（${fromBinding.nodeName}）` : ''
  try {
    await ElMessageBox.confirm(
      `本机当前绑定的是节点 ${from}${fromName}，即将登录 ${toNodeId}。\n`
      + '登录后本机会改为只服务新节点，旧的绑定与登录身份将被清除；'
      + `此后 ${from} 要在这台浏览器上重新登录，需要管理员重新签发激活凭证。`,
      '切换绑定节点',
      {
        confirmButtonText: '清除旧绑定并登录',
        cancelButtonText: '取消',
        type: 'warning',
        // 多行文案 + 节点编号会被默认宽度折得很难读
        customClass: 'node-switch-confirm'
      }
    )
    return true
  } catch {
    return false
  } finally {
    switchingNode.value = false
  }
}

/**
 * 清除新节点之外的全部绑定与登录身份（**只清本机**）。
 *
 * 服务端登记的公钥**不动** —— 清掉的是本机的私钥与记账，不是服务端的授权。
 * 原因写在这里免得后人"顺手"去改服务端：那会让另一个节点在别的设备上也登录不了。
 */
async function purgeOtherBindings(keepNodeId) {
  try {
    const removed = await clearOtherBindings(keepNodeId)
    const count = (removed?.bindingsRemoved || []).length
    if (count > 0) {
      ElMessage.info(`已清除本机其它 ${count} 个节点的绑定`)
    }
  } catch (error) {
    // 清不掉不该阻断进站：用户已经登录成功了。但要如实说出来 ——
    // 静默失败会让"本机只绑定一个节点"这个前提悄悄不成立。
    ElMessage.warning(`旧绑定清除未完成：${error?.message || '未知原因'}`)
  }
}

/** 登录/激活成功后的统一收尾：跳根路径，由守卫按服务端身份分流。 */
async function enterAfterNodeLogin() {
  router.push({ path: '/' })
}

function getCode() {
  getCodeImg().then(res => {
    captchaEnabled.value = res.captchaEnabled === undefined ? true : res.captchaEnabled;
    if (captchaEnabled.value) {
      codeUrl.value = "data:image/jpeg;base64," + res.img;
      loginForm.value.uuid = res.uuid;
    }
  });
}

function getCookie() {
  const username = Cookies.get("username");
  const password = Cookies.get("password");
  const rememberMe = Cookies.get("rememberMe");
  // ⚠️ 必须**合并**而不是整体替换。整体替换会把 `uuid`/`code`/`declaredPrincipal`
  //    一并丢掉，只因为 getCode() 的响应恰好在这次替换之后到达而侥幸没坏 ——
  //    那是时序巧合，不是保证（getCode 是异步的）。一旦它先返回，
  //    登录会带着空 uuid 提交，服务端验证码校验失败，且现象只是"验证码错误"，
  //    很难反查到是这里覆盖了表单。
  loginForm.value = {
    ...loginForm.value,
    username: username === undefined ? loginForm.value.username : username,
    password: password === undefined ? loginForm.value.password : decrypt(password),
    rememberMe: rememberMe === undefined ? false : Boolean(rememberMe)
  };
}

getCode();
getCookie();
</script>

<style lang='scss' scoped>
.login {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  position: relative;
  background-image: url("../assets/images/login-background.jpg");
  background-size: cover;
  background-position: center;
}

/* 背景为亮色调实景照，加一层压暗叠加以保证标题/页脚文字对比度 */
.login::before {
  content: "";
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  pointer-events: none;
}

.login > * {
  position: relative;
  z-index: 1;
}

/* 标题位于白色登录卡片内部，故用深色文字（此前误设为反色白字） */
.title {
  margin: 0px auto 30px auto;
  text-align: center;
  color: var(--kms-text-primary);
  font-weight: 600;
}

.login-form {
  border-radius: var(--kms-radius-lg);
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  box-shadow: var(--kms-shadow-lg);
  width: 400px;
  padding: 25px 25px 5px 25px;
  .el-input {
    height: 40px;
    input {
      height: 40px;
    }
  }
  .input-icon {
    height: 39px;
    width: 14px;
    margin-left: 0px;
  }
}
.login-tip {
  font-size: 13px;
  text-align: center;
  color: var(--kms-text-secondary);
}

/* 身份选择：占满卡片宽度，两个页签等分，视觉上与下方表单成为一组 */
.principal-switch {
  display: flex;
  width: 100%;
  margin-bottom: 10px;
}

.principal-switch :deep(.el-radio-button),
.principal-switch :deep(.el-radio-button__inner) {
  flex: 1;
}

.principal-switch :deep(.el-radio-button__inner) {
  width: 100%;
}

.principal-hint {
  margin: 0 0 18px;
  min-height: 34px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--kms-text-secondary);
}

/* 已激活节点列表：本机 IndexedDB 里有设备私钥的节点 */
.activated-block {
  margin-bottom: 16px;
}

.activated-title {
  font-size: 12px;
  color: var(--kms-text-secondary);
  margin-bottom: 8px;
}

.activated-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow-y: auto;
}

.activated-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius-md, 8px);
  background: var(--kms-surface-2, #fafafa);
  color: var(--kms-text-primary);
  font: inherit;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.activated-item:hover:not(:disabled) {
  border-color: var(--kms-brand-border, #1677ff);
  background: var(--kms-surface-3, #f0f2f5);
}

.activated-item:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.activated-name {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 节点名 + 绑定信息（最近登录）纵向排列；右侧仍是「点击登录」 */
.activated-main {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

.activated-meta {
  font-size: 11px;
  color: var(--kms-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.activated-action {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--kms-text-secondary);
}

.activated-empty {
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px dashed var(--kms-border);
  border-radius: var(--kms-radius-md, 8px);
  font-size: 12px;
  line-height: 1.6;
  color: var(--kms-text-secondary);
}

/* 「登录其它节点」：有可免密登录的节点时才出现，占满宽度、弱化（plain），
   让视线先落在上面的节点条目上。 */
.switch-node-btn {
  width: 100%;
  margin-top: 4px;
}

/* 展开新节点表单时的上下文说明：说清"这一步会替换掉上面那个节点的登录信息"，
   否则用户以为"多登一个"只是多一份，不会想到是**换**。 */
.form-context {
  margin-bottom: 14px;
  padding: 8px 10px;
  border-radius: var(--kms-radius-md, 8px);
  background: var(--kms-surface-2, #fafafa);
  font-size: 12px;
  line-height: 1.7;
  color: var(--kms-text-secondary);
}
.form-context .mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  color: var(--kms-text-primary);
}

.login-code {
  width: 33%;
  height: 40px;
  float: right;
  img {
    cursor: pointer;
    vertical-align: middle;
  }
}
.el-login-footer {
  height: 40px;
  line-height: 40px;
  position: fixed;
  bottom: 0;
  width: 100%;
  text-align: center;
  color: var(--kms-text-inverse);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  font-family: var(--kms-font-sans);
  font-size: 12px;
  letter-spacing: 1px;
}
.login-code-img {
  height: 40px;
  padding-left: 12px;
}
</style>

<style>
/* 「切换绑定节点」确认框是 MessageBox 挂到 body 上的，**不在本组件的 DOM 里**，
   scoped 样式到不了；而多行文案 + 节点编号在默认宽度下会被折成很难读的样子。
   这里收窄字号、放开行高，让那段说明是一次能读完的。 */
.node-switch-confirm .el-message-box__message {
  line-height: 1.7;
}
.node-switch-confirm .el-message-box__message p {
  white-space: pre-line;
}
</style>
