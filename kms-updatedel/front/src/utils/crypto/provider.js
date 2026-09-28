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
  const text = String(name || '').trim().toUpperCase().replace(/^CL-/, '')
  if (text.includes('KYBER') || text === 'ML-KEM') {
    return 'KYBER'
  }
  if (text.includes('FALCON')) {
    return 'FALCON'
  }
  if (text.includes('SSCL')) {
    return 'SSCL'
  }
  if (text.includes('SM2')) {
    return 'SM2'
  }
  return text
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
