/**
 * `CryptoProvider` —— 节点侧密码能力的**统一抽象**（文档 §4.4）。
 *
 * 为什么要有这层抽象
 * ------------------
 * §4.4 的原话是：「密码能力通过统一 CryptoProvider 抽象，未来可增加
 * AgentCryptoProvider，将秘密材料迁移到节点本地 Agent、TPM 或 HSM，
 * **而不修改上层生命周期业务逻辑**」。
 *
 * 所以这个文件的产物不是"多一层调用"，而是**一条边界**：
 * 上层（密钥生成页、节点初始化页、分发取件页）只认下面这几个方法，
 * 不知道私钥存在哪、由谁算。
 *
 * 今天只有一个实现（`BrowserCryptoProvider`，浏览器即节点侧运行环境），
 * 因此**刻意不做**注册表 / 工厂 / 插件发现这类前瞻复杂度 ——
 * 那是在给一个还不存在的第二实现写胶水。等真要做 Agent 时再加，
 * 那时改动只落在这个文件与它的实现上，上层一行不动。
 *
 * 术语
 * ----
 * - `algorithm`：`SM2` / `SSCL` / `KYBER` / `FALCON`（大小写不敏感）
 * - `keyRef`：私密材料的**逻辑引用**。上层拿它指代"哪份密钥"，
 *   但拿不到材料本身 —— 材料只存在于 provider 内部的密钥库里。
 *   这是"上层不接触私钥"这条要求在类型层面的体现。
 * - `publicKey`：公开量。可以自由落库、上报、展示。
 */

export const ALGORITHMS = ['SM2', 'SSCL', 'KYBER', 'FALCON']

/** 归一算法名。库里历史写法混杂（`Kyber` / `KYBER` / `CL-Kyber`），统一收口。 */
export function normalizeAlgorithm(name) {
  const text = String(name || '').trim().toUpperCase()
  // Exact historical aliases only. Unknown derivative/scheme IDs must not collapse
  // into a supported core, and ML-KEM is not the round-3 Kyber wire protocol.
  const aliases = {
    KYBER: 'KYBER', 'CL-KYBER': 'KYBER', KYBER_KEM: 'KYBER', PQ_KYBER: 'KYBER', PQ_CL_KYBER: 'KYBER',
    FALCON: 'FALCON', 'CL-FALCON': 'FALCON', FALCON_LATTICE: 'FALCON', PQ_FALCON: 'FALCON', PQ_CL_FALCON: 'FALCON',
    SSCL: 'SSCL', 'CL-SSCL': 'SSCL', GM_SSCL: 'SSCL',
    SM2: 'SM2', 'CL-SM2': 'SM2', GM_SM2: 'SM2'
  }
  return aliases[text] || text
}

/**
 * 抽象基类。方法体一律抛错 —— 它存在的意义是**声明契约**，
 * 不是提供默认实现。子类没实现的方法会在这里明确失败，
 * 而不是在某条业务路径深处炸出一个 `undefined is not a function`。
 */
export class CryptoProvider {
  /**
   * 生成一份新的密钥材料。
   *
   * 私密部分**留在 provider 内部**（落进节点本地密钥库），
   * 返回值里只有公开量与引用。
   *
   * @param {string} algorithm
   * @param {object} [options] 算法相关选项（如 Kyber 变体、SSCL 公共参数）
   * @param {Function} [options.issueKeygen] KYBER/FALCON 必需的经认证发放回调；provider 不直接发网络请求
   * @param {object} [options.generationContext] PQ 必需：当前可信 nodeId/userId/bindingKind/deviceFingerprint/demoSessionId/demoRevision，核对服务端响应
   * 新 PQ 生成返回 generation（方案/不可变发放/可续期授权引用）和 generationContext。
   * 已封存 keyRef 必须由生命周期层复用或恢复；generate 永不覆盖它。
   * @returns {Promise<{publicKey: string, keyRef: string, algorithm: string}>}
   */
  async generate(algorithm, options = {}) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 generate`)
  }

  /** 用 `keyRef` 对应的私钥对消息签名 */
  async sign(algorithm, keyRef, message) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 sign`)
  }

  /** 用**公钥**验签。不需要 keyRef —— 验签本来就不该接触私钥。 */
  async verify(algorithm, publicKey, signature, message) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 verify`)
  }

  /** 解封装（Kyber）：用 `keyRef` 的私钥把密文还原成共享密钥 */
  async decapsulate(algorithm, keyRef, ciphertext) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 decapsulate`)
  }

  /**
   * 封装（Kyber）：用**公钥**产生 `(ciphertext, sharedSecret)`。
   *
   * 与 `decapsulate` 成对。发送节点在**收件方公钥**上做这一步，
   * 收件节点用自己的私钥解开 —— 公钥是公开量，所以这里收的是 publicKey
   * 而不是 keyRef（与 `verify` 同一口径）。
   *
   * 返回的 `sharedSecret` 是**原始字节**，怎么用由调用方决定
   * （分发流程按既有口径取前 16 字节当 SM4 的 KEK）。
   *
   * @param {string} algorithm
   * @param {string} publicKey
   * @returns {Promise<{ciphertext: Uint8Array, sharedSecret: Uint8Array, algorithm: string}>}
   */
  async encapsulate(algorithm, publicKey) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 encapsulate`)
  }

  /**
   * 用**接收方的公钥**把载荷密钥封成一份可直接落库、对面可直接解的**节点腿信封**。
   *
   * 与 `encapsulate` 的区别是层次：那个是 KEM **原语**（返回密文与共享秘密，
   * 组合与编码由调用方负责）；本方法产出**成品**，形状与服务端
   * `wrappers.wrap_with_public_key` 逐字段对应，对面拿 `unwrapEnvelope` 就能解。
   *
   * 支持 KYBER / SM2 / SSCL（计划 §3 的保护算法白名单）。
   *
   * @param {string} algorithm
   * @param {string} recipientPublicKeyHex
   * @param {Uint8Array} payloadKey 16 字节 SM4 载荷密钥
   * @returns {Promise<{envelope: object, wrapping: string}>}
   */
  async wrapForPeer(algorithm, recipientPublicKeyHex, payloadKey) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 wrapForPeer`)
  }

  /**
   * 自检：**用这份材料真的做一轮加解密/签名验证**，而不是"看着是好的"。
   *
   * 存在理由是密钥库里躺着的材料可能是**上一代格式**或**别的算法**的：
   * 长度对得上、字段齐全、但用起来才失败。生成页在"当前生产版本"旁边
   * 显示自检结论，就是为了把"登记成功了"与"这把真能用"分开 ——
   * 两者混为一谈时，故障要等到真正分发时才现形（那时已经是别人的会话）。
   *
   * 实现必须**只用本地材料**：任何"拿去问服务端"的做法都会在离线/服务端
   * 不可达时给出误导性的失败。
   *
   * @param {string} algorithm
   * @param {string} keyRef
   * @returns {Promise<{ok: boolean, detail: string}>} 不抛错 —— 失败是结论的一种
   */
  async selfTest(algorithm, keyRef) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 selfTest`)
  }

  /** 解开一个分发信封（SM2 / SSCL / Kyber），返回其中的载荷密钥 */
  async unwrapEnvelope(algorithm, keyRef, envelope) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 unwrapEnvelope`)
  }

  /** 该引用在本地是否可用（用于设备绑定判断：新设备上这里会是 false） */
  async hasKey(keyRef) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 hasKey`)
  }

  /** 销毁一份本地私密材料 */
  async destroy(keyRef) { // eslint-disable-line no-unused-vars
    throw new Error(`${this.constructor.name} 未实现 destroy`)
  }
}
