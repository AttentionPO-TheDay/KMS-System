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
        <div v-if="activatedNodes.length" class="activated-block">
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
              <span class="activated-name">{{ id }}</span>
              <span class="activated-action">{{ busyNode === id ? '登录中…' : '点击登录' }}</span>
            </button>
          </div>
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

      <!-- 节点首次激活：节点名 + 一次性凭证，没有口令 -->
      <template v-else>
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
          <el-input
            v-model="loginForm.activationCode"
            type="text"
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
          v-else
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
import { ElMessage } from "element-plus";
import { encrypt, decrypt } from "@/utils/jsencrypt";
import { listActivatedNodes } from '@/utils/crypto/device-credential';
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
 * 正在免输入登录的节点 id；空串表示没有在忙。
 *
 * ⚠️ 模板里**不要**直接把它绑给 `:disabled` —— 用 `anyNodeBusy` 那个布尔。
 *    绑字符串会踩到 HTML 布尔属性的坑：空串在 `disabled` 这类属性上
 *    并不总是等价于 false，实测（2026-09-30）按钮一直是禁用态，
 *    而"点不动"被误读成"点击没反应"，查了半天。
 */
const busyNode = ref('')
const anyNodeBusy = computed(() => busyNode.value !== '')

async function refreshActivatedNodes() {
  if (!isNodeMode.value) {
    activatedNodes.value = []
    return
  }
  activatedNodes.value = await listActivatedNodes()
}

watch(isNodeMode, (nodeMode) => {
  if (nodeMode) {
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
function handleNodeActivate() {
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
  userStore.activateNodeWithCode({ nodeId, code })
    .then(() => {
      // 激活成功：本机现在有该节点的设备凭据了。
      // 后续所有登录都走挑战-应答，不再需要凭证。
      loading.value = false
      ElMessage.success('激活成功，正在进入…')
      router.push({ path: '/' })
    })
    .catch((error) => {
      loading.value = false
      ElMessage.error(error?.message || '激活失败')
    })
}

/** 已激活节点：点一下就走挑战-应答，不输入任何东西 */
function handleQuickLogin(nodeId) {
  if (anyNodeBusy.value) {
    return
  }
  busyNode.value = nodeId
  userStore.loginAsActivatedNode(nodeId)
    .then(() => {
      busyNode.value = ''
      router.push({ path: '/' })
    })
    .catch((error) => {
      busyNode.value = ''
      ElMessage.error(error?.message || '登录失败')
      // 失败可能是本机凭据与服务端登记的不一致（换过设备/清过数据）。
      // 刷新一次列表，让"其实用不了"的节点不再显示成可点。
      refreshActivatedNodes()
    })
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
