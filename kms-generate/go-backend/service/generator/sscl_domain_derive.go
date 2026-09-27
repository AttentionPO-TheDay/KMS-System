package generator

import (
	"math/big"
	"strconv"

	"github.com/tjfoc/gmsm/sm3"
)

// =============================================================================
// SSCL 域参数的确定性派生（Go 侧）
// -----------------------------------------------------------------------------
// 【原来错在哪】
//   newSSCLGenerator() 过去用 mustRand(n) 随机抽 wa、coefficients[1..T] 和
//   xIndexs[0..T-1]。后果有两个，第二个此前无人发现：
//     1. 不抗重启：SSCL 把这些多项式的份额当作"公开参数"经 GET /comparam 发布，
//        而域秘密藏在常数项 coefficients[0] = ms*wa mod n 里。进程每次重启都换一套
//        随机参数，于是已签发密钥里存的 SSCLKey/SSCLEA 与重启后发布的参数不再对应，
//        客户端在 x=0 处拉格朗日插值出来的是垃圾。
//     2. 跨语言不一致（更严重）：/comparam 由 Go 服务提供，但生命周期 update 路径的
//        SSCL 密钥材料由 Java 的 SsclKeyGenerator 用**它自己独立随机**的系数生成。
//        于是 my = g(mx) 落在 Java 的多项式 g 上，而 (xIndexs[i], yIndexs[i]) 落在
//        Go 的多项式 f 上；T+1 个点根本不在同一条 T 次多项式上，插值必然失败。
//        也就是说 update 路径产出的 SSCL 密钥此前就是不可用的。
//
// 【现在的做法】
//   把域参数改成**主私钥 ms 的确定性函数**（标准 SM3，无任何随机源）：
//
//     msBytes   = ms 的 32 字节大端表示（ms 是 64 位十六进制字符串解析出的整数）
//     counter   = 单字节大端，从 0x00 起，被拒则 +1
//     derive(label):
//         for counter in 0x00..0xFF:
//             candidate = BigInteger(1, SM3(msBytes || utf8(label) || counter))
//             if 1 <= candidate < n: return candidate
//         raise error（实际不可能发生：单次被拒概率约 2^-32）
//
//     wa      = derive("KMS-SSCL-DOMAIN-v1|wa")
//     coef[0] = (ms * wa) mod n                                  <-- 不是哈希出来的
//     coef[i] = derive("KMS-SSCL-DOMAIN-v1|coef|" + i)    i = 1..T（十进制，不补零）
//     x[i]    = 见 deriveDomainXIndex，i = 1..T（仅 Go 需要；Java 不发布评测点）
//     y[i]    = polynomial(coef, x[i]) mod n（沿用原 computeShareInternal，未改动）
//
//   coef[0] 必须留在 ms*wa mod n 上，不能改成哈希值：既有关系
//     SSCLEA = coef[0]  且  客户端 dA = 插值常数项 * m mod n
//   依赖它；改了就会破坏所有已签发密钥的可用性。
//
// 【必须同步修改】
//   本文件与 Java 侧
//     kms-updatedel/java-backend/ruoyi-admin/src/main/java/com/ruoyi/updatedel/service/generator/SsclKeyGenerator.java
//   是**同一条派生规则的镜像实现**，两边的标签字符串、字节序、拒绝条件必须逐字节一致。
//   只用其中一边修改 = 客户端拿到的 T+1 个点不在同一条多项式上 = 插值出垃圾。
//   改任意一边都必须同时改另一边，并用跨语言测试比对派生结果（见 sscl_generator_test.go
//   中的确定性测试 + 手工跨语言比对）。
//
// 【轮换 ms 的影响】
//   域参数完全由 ms 决定，所以轮换 KGC_MASTER_SECRET 会**同时改变** wa、coef[1..T]、
//   xIndexs、yIndexs、coef[0]（进而 SSCLEA）以及 PPub = ms*G。存量密钥必须整体重新登记，
//   否则旧密钥的客户端私钥与新的公开参数不再匹配。详见 doc/kms-restructure-plan.md 的 R17。
// =============================================================================

// domainLabelPrefix 是所有派生标签的统一前缀（ASCII，区分大小写，不得改动）。
const domainLabelPrefix = "KMS-SSCL-DOMAIN-v1|"

// sm3DigestSize 是标准 SM3 的输出长度（字节）。
const sm3DigestSize = 32

// domainLabelWA 返回 wa 的派生标签。
func domainLabelWA() string { return domainLabelPrefix + "wa" }

// domainLabelCoef 返回第 i 个非常数项系数的派生标签（i 为十进制，不补零）。
func domainLabelCoef(i int) string { return domainLabelPrefix + "coef|" + strconv.Itoa(i) }

// domainLabelX 返回第 index 个评测点在第 attempt 次尝试时的派生标签。
func domainLabelX(index int, attempt int) string {
	return domainLabelPrefix + "x|" + strconv.Itoa(index) + "|" + strconv.Itoa(attempt)
}

// deriveDomainScalar 用 SM3 从主私钥 ms 确定性地派生一个 [1, n) 范围内的标量。
//
// 与随机抽样的区别：同一把 ms + 同一个 label 在任何机器、任何时刻、任何进程里
// 都必须得到同一个值——这正是修复"重启后 SSCL 公开参数漂移"的关键。
//
// label 必须与 Java 侧逐字节一致（UTF-8、无长度前缀、无终止符）。
// 若 256 次计数全部落在 [1, n) 之外（概率约 2^-256，实际不可能）则 panic：
// 这种情况下静默返回一个错误值会把不可用的公开参数发出去，比直接失败危险得多。
func deriveDomainScalar(ms *big.Int, label string, n *big.Int) *big.Int {
	msBytes := make([]byte, 32)
	ms.FillBytes(msBytes)
	labelBytes := []byte(label)
	counter := make([]byte, 1)
	digest := make([]byte, sm3DigestSize)

	for c := 0; c <= 0xFF; c++ {
		counter[0] = byte(c)
		h := sm3.New()
		h.Write(msBytes)
		h.Write(labelBytes)
		h.Write(counter)
		sum := h.Sum(digest[:0])
		candidate := new(big.Int).SetBytes(sum)
		if candidate.Sign() > 0 && candidate.Cmp(n) < 0 {
			return candidate
		}
	}

	panic("SSCL 域参数派生失败：SM3 计数器 0x00..0xFF 全部被拒（label=" + label + "）")
}

// deriveDomainXIndex 派生第 index 个（1-based）评测点 x[index]。
//
// 规则被显式钉死，以保证 Go 跨进程、跨版本完全可复现：
//   - attempt 从 0 递增到 255；
//   - 每个 attempt 先用 deriveDomainScalar 派生候选值（candidate 天然 >= 1）；
//   - 候选值不得为 0，且不得与已接受集合 accepted 中的任何值重复；
//   - 第一个满足条件的候选值胜出（first non-colliding attempt wins）。
//
// 碰撞概率极低（生日界下约 2^-250 量级），但规则必须写死，
// 否则"哪一次尝试被接受"就成了不确定行为。
func deriveDomainXIndex(ms *big.Int, index int, n *big.Int, accepted []*big.Int) *big.Int {
	for attempt := 0; attempt <= 0xFF; attempt++ {
		candidate := deriveDomainScalar(ms, domainLabelX(index, attempt), n)
		if candidate.Sign() == 0 {
			continue
		}
		duplicated := false
		for _, prev := range accepted {
			if prev.Cmp(candidate) == 0 {
				duplicated = true
				break
			}
		}
		if !duplicated {
			return candidate
		}
	}

	panic("SSCL 评测点派生失败：x|" + strconv.Itoa(index) + " 的 256 次尝试全部碰撞")
}
