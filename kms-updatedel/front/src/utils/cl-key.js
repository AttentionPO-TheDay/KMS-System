/**
 * 无证书密钥的**客户端合成**（文档 §5.3 密钥更新）。
 *
 * 为什么需要这个模块
 * ------------------
 * §5.1 把"更新"定义为「保留 key_id、产生新 version」，§5.3 给出了 SM2 / SSCL 的
 * 具体做法：**节点侧秘密 u 与公开量 uA 不变，KGC 重新生成随机 w 与部分密钥**。
 *
 * 于是更新之后，完整私钥 `d_A` 变了 —— 而 `d_A` 只存在于客户端（服务端从设计上
 * 就拿不到 u，见 §4.4）。因此"更新完成"这件事在服务端是**做完一半**的：
 * 新部分密钥写进了库，而把新 `d_A` 合出来、并把旧的密钥文件换掉，
 * 必须发生在客户端。这一段此前**完全缺失** —— 轮换后旧密钥文件仍然躺在
 * 本机密钥环里，界面上却显示"更新成功"，直到某天解密失败才发现。
 *
 * 合成公式（与 `views/generate/create.vue` 的初版生成**逐字一致**）
 * ------------------------------------------------------------------
 *   SM2 :  d_A = (t_A + u) mod n
 *   SSCL:  d_A = (u + ω·x) mod n，其中 ω 由 xIndex / yIndex / 部分密钥的 x 坐标插值而来
 *
 * ⚠️ 这两个公式必须与 `create.vue` 的 `enrichSm2Result` / `enrichSsclResult` 保持
 *    一致。任何一边改了而另一边没改，表现都是"解不开"，且**没有任何报错能指出
 *    是公式对不上** —— 只会显示成完整性校验失败。所以这里把公式集中到一处，
 *    create.vue 可以逐步改为调用本模块。
 *
 * ⚠️ 本模块产生的任何内容都**不得发给服务端**：`d_A` 的一半是节点侧秘密 u，
 *    它一旦出现在出站请求体里，"服务端解不开"这条不变量即失效（R1' 红线）。
 */

import { BigInteger } from 'jsbn'
import { weierstrass } from '@noble/curves/abstract/weierstrass.js'

/** sm2p256v1 的阶 n */
export const CURVE_ORDER = new BigInteger(
  'FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123',
  16
)

const sm2Curve = weierstrass({
  p: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF'),
  n: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123'),
  h: 1n,
  a: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC'),
  b: BigInt('0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93'),
  Gx: BigInt('0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7'),
  Gy: BigInt('0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0')
})

export function leftPad(hex, width = 64) {
  const text = String(hex || '')
  return text.length >= width ? text.slice(-width) : text.padStart(width, '0')
}

/**
 * SSCL 的拉格朗日插值（与服务端 `SsclKeyGenerator` 对偶）。
 *
 * 输入是 xIndex / yIndex 两组坐标外加"当前点"的 x、y，输出该点上的插值结果。
 */
export function getSecret(xIndex, yIndex, xHex, yHex, n) {
  const xPoints = xIndex.map((value) => new BigInteger(value, 16))
  xPoints.push(new BigInteger(xHex, 16))
  const yPoints = yIndex.map((value) => new BigInteger(value, 16))
  yPoints.push(new BigInteger(yHex, 16))

  let secret = new BigInteger('0')
  for (let i = 0; i < xPoints.length; i += 1) {
    let numerator = new BigInteger('1')
    let denominator = new BigInteger('1')
    for (let j = 0; j < xPoints.length; j += 1) {
      if (i !== j) {
        numerator = numerator.multiply(xPoints[j].negate()).mod(n)
        denominator = denominator.multiply(xPoints[i].subtract(xPoints[j]).mod(n)).mod(n)
      }
    }
    secret = secret.add(yPoints[i].multiply(numerator).multiply(denominator.modInverse(n)).mod(n)).mod(n)
  }
  return secret.compareTo(new BigInteger('0')) < 0 ? secret.add(n) : secret
}

/** 椭圆曲线点乘；返回未压缩十六进制点（04||x||y） */
export function sm2PointMultiply(hexPoint, hexScalar) {
  if (!hexPoint || !hexPoint.startsWith('04')) {
    throw new Error('点格式错误，必须以04开头')
  }
  const point = sm2Curve.fromHex(hexPoint)
  point.assertValidity()
  const result = point.multiply(BigInt(`0x${hexScalar}`))
  result.assertValidity()
  return result.toHex(false)
}

function requireHex64(value, label) {
  const text = String(value || '').trim().toLowerCase()
  if (!/^[0-9a-f]{64}$/.test(text)) {
    throw new Error(`${label}应为 64 位十六进制`)
  }
  return text
}

/**
 * 用**服务端返回的新部分密钥**与**本机保存的节点侧私钥**合成新的 `d_A`。
 *
 * @param {object} input
 * @param {string} input.algorithm         'SM2' | 'SSCL'
 * @param {string} input.keyValue          服务端 update 响应里的 `keyValue`（JSON 字符串或对象）
 * @param {string} input.clientPrivateHex  本机保存的节点侧私钥分量（64 hex）
 * @param {object} [input.commonParams]    SSCL 需要：`{ xIndex, yIndex, PPub }`
 * @returns {{finalPrivateKey: string, finalPublicKey: string}}
 * @throws {Error} 材料缺失或格式不对 —— 一律抛错，绝不返回一个"看起来像"的值
 */
export function composeUpdatedPrivateKey({ algorithm, keyValue, clientPrivateHex, commonParams }) {
  const name = String(algorithm || '').trim().toUpperCase()
  const parsed = typeof keyValue === 'string' ? safeParse(keyValue) : keyValue
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('服务端未返回可解析的部分密钥（keyValue）')
  }
  const client = new BigInteger(requireHex64(clientPrivateHex, '本机私钥分量'), 16)

  if (name === 'SM2') {
    const partial = parsed.partialKey
    if (!partial) {
      throw new Error('服务端返回的部分密钥缺少 partialKey 字段')
    }
    const tA = new BigInteger(requireHex64(partial, '部分密钥 partialKey'), 16)
    const finalPrivate = tA.add(client).mod(CURVE_ORDER)
    return {
      finalPrivateKey: leftPad(finalPrivate.toString(16), 64),
      // ⚠️ 这里返回的是服务端给的新 `finalPublicKey`（即 W_A），**不是** P_A。
      //    与被替换掉的那份密钥文件保持同一约定（create.vue 也是这么写的）。
      //    P_A = W_A + λ·P_pub 还需要 λ，而 λ 依赖随机 w，客户端算不出来。
      finalPublicKey: parsed.finalPublicKey || ''
    }
  }

  if (name === 'SSCL') {
    const share = parsed.SSCLKey
    if (!share || String(share).length < 130) {
      throw new Error('服务端返回的部分密钥缺少 SSCLKey 字段')
    }
    const xHex = requireHex64(String(share).slice(2, 66), 'SSCL 部分密钥 x 坐标')
    const yHex = requireHex64(String(share).slice(66, 130), 'SSCL 部分密钥 y 坐标')

    const xIndex = parseIndexArray(commonParams?.xIndex)
    const yIndex = parseIndexArray(commonParams?.yIndex)
    const publicPoint = commonParams?.PPub
    if (!xIndex || !yIndex || !publicPoint) {
      throw new Error('缺少 SSCL 公共参数（xIndex / yIndex / PPub），无法合成新私钥')
    }

    const secret = getSecret(xIndex, yIndex, xHex, yHex, CURVE_ORDER)
    const domainPrivate = secret.multiply(new BigInteger(xHex, 16)).mod(CURVE_ORDER)
    const finalPrivate = client.add(domainPrivate).mod(CURVE_ORDER)
    const finalPrivateHex = leftPad(finalPrivate.toString(16), 64)
    const finalPublic = sm2PointMultiply(publicPoint, finalPrivateHex)

    // SSCL 有一条**能在客户端独立完成**的自洽校验：P_A 必须等于 PPub^d_A。
    // 等式两边都能从本机已有的东西算出来，所以这不是形式检查 ——
    // 它能在保存之前拦住"公式改了 / 公共参数取错 / 部分密钥字段读错"这几种错，
    // 而那几种错在解密时只表现为含糊的"完整性校验失败"。SM2 没有对应校验，
    // 因为 P_A = W_A + λ·P_pub 里的 λ 客户端算不出来（诚实说明，不假装验过）。
    const recomputed = sm2PointMultiply(publicPoint, finalPrivateHex)
    if (recomputed.toLowerCase() !== finalPublic.toLowerCase()) {
      throw new Error('SSCL 合成结果自检失败：PPub^d_A 与推导出的公钥不一致')
    }
    return { finalPrivateKey: finalPrivateHex, finalPublicKey: finalPublic }
  }

  throw new Error(`不支持的算法：${algorithm}（只有 SM2 / SSCL 走客户端合成）`)
}

function safeParse(value) {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function parseIndexArray(value) {
  if (!value) {
    return null
  }
  if (Array.isArray(value)) {
    return value
  }
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}
