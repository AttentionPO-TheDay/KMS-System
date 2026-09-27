package generator

import (
	"crypto/elliptic"
	"encoding/hex"
	"errors"
	"hash"
	"io"
	"math/big"
	"strings"
	"sync"

	"key-service-generate/config"
	"key-service-generate/models"

	"github.com/tjfoc/gmsm/sm2"
	"github.com/tjfoc/gmsm/sm3"
)

// =============================================================================
// SSCL 生成器：域参数由主私钥 ms 确定性派生（不再依赖任何随机源）
// -----------------------------------------------------------------------------
// 公开参数（wa、coefficients[1..T]、xIndexs、yIndexs）现在都是 ms 的确定性函数，
// 因此：
//   * 进程重启、扩容多副本、构建新镜像，派生出的公开参数都**完全一致**，
//     已签发密钥里的 SSCLKey/SSCLEA 不会因为重启而失配；
//   * Go（本文件，服务 GET /comparam）与 Java
//     （kms-updatedel/java-backend/.../service/generator/SsclKeyGenerator.java，
//      生命周期 update 路径生成 SSCL 密钥）落在**同一条多项式**上，
//     客户端的 T+1 个插值点重新共线，x=0 处的拉格朗日插值才能还原常数项。
//
// 两个实现必须保持逐字节镜像：标签字符串、字节序、拒绝条件都一样才算一致。
// 派生规则与完整说明见 sscl_domain_derive.go。
//
// 轮换 KGC_MASTER_SECRET（ms）会改变以上全部公开参数以及 PPub = ms*G，
// 存量密钥必须整体重新登记；详见 doc/kms-restructure-plan.md 的 R17。
// =============================================================================

type SSCLGenerator struct {
	curve        elliptic.Curve
	n            *big.Int
	ms           *big.Int
	coefficients []*big.Int
	t            int

	gStr    string
	pPubStr string

	xIndexs []*big.Int
	yIndexs []*big.Int

	ctxPool sync.Pool
}

type ssclWorkerCtx struct {
	mx        *big.Int
	my        *big.Int
	tempPow   *big.Int
	tempMul   *big.Int
	tempSum   *big.Int
	ux        *big.Int
	uy        *big.Int
	hasher    hash.Hash
	buffer    []byte
	temp32    []byte
	temp32Arr [32]byte
}

var (
	globalSSCLGen *SSCLGenerator
	ssclOnce      sync.Once
)

func GetSSCLGenerator() *SSCLGenerator {
	ssclOnce.Do(func() {
		globalSSCLGen = newSSCLGenerator()
	})
	return globalSSCLGen
}

func newSSCLGenerator() *SSCLGenerator {
	c := sm2.P256Sm2()
	n := c.Params().N
	gx, gy := c.Params().Gx, c.Params().Gy

	// 主私钥来自统一配置源（KGC_MASTER_SECRET），不再硬编码。
	ms, _ := new(big.Int).SetString(config.KgcMasterSecret, 16)

	xPPub, yPPub := c.ScalarMult(gx, gy, ms.Bytes())

	gStr := makePointStr(gx, gy)
	pPubStr := makePointStr(xPPub, yPPub)

	t := 10
	coefficients := make([]*big.Int, t+1)

	// 域参数全部由主私钥 ms 确定性派生，不再使用随机源：
	// 否则每次重启都会换一套 wa/coef/xIndexs，已签发密钥存的 SSCLKey/SSCLEA
	// 就与 /comparam 新发布的公开参数对不上；而且 Java 侧会独立随机出另一条多项式，
	// 使客户端拿到的 T+1 个点根本不在同一条 T 次多项式上。
	// 派生规则、标签字符串与"必须与 Java 镜像同步"的说明见 sscl_domain_derive.go。
	wa := deriveDomainScalar(ms, domainLabelWA(), n)
	eA := new(big.Int).Mul(ms, wa)
	eA.Mod(eA, n)
	coefficients[0] = eA

	for i := 1; i <= t; i++ {
		coefficients[i] = deriveDomainScalar(ms, domainLabelCoef(i), n)
	}

	xIndexs := make([]*big.Int, t)
	yIndexs := make([]*big.Int, t)

	tempCtx := &ssclWorkerCtx{
		tempPow: new(big.Int),
		tempMul: new(big.Int),
		tempSum: new(big.Int),
		my:      new(big.Int),
	}

	for i := 0; i < t; i++ {
		// x 下标按 1-based 派生（x[1]..x[T] 对应 xIndexs[0]..xIndexs[T-1]），
		// 已被接受的 x 作为"已接受集合"传入，用于按 first-non-colliding 规则去重。
		xIndexs[i] = deriveDomainXIndex(ms, i+1, n, xIndexs[:i])
		yIndexs[i] = computeShareInternal(coefficients, xIndexs[i], n, tempCtx)
		yIndexs[i] = new(big.Int).Set(yIndexs[i])
	}

	gen := &SSCLGenerator{
		curve:        c,
		n:            n,
		ms:           ms,
		coefficients: coefficients,
		t:            t,
		gStr:         gStr,
		pPubStr:      pPubStr,
		xIndexs:      xIndexs,
		yIndexs:      yIndexs,
		ctxPool: sync.Pool{
			New: func() interface{} {
				ctx := &ssclWorkerCtx{
					mx:      new(big.Int),
					my:      new(big.Int),
					tempPow: new(big.Int),
					tempMul: new(big.Int),
					tempSum: new(big.Int),
					ux:      new(big.Int),
					uy:      new(big.Int),
					hasher:  sm3.New(),
					buffer:  make([]byte, 0, 1024),
				}
				ctx.temp32 = ctx.temp32Arr[:]
				return ctx
			},
		},
	}
	return gen
}

func (gen *SSCLGenerator) GenPartialKey(identityData string, uAStr string, keyDomain string, keyUse string) (models.Keymanage, error) {
	if len(uAStr) != 130 || !strings.HasPrefix(uAStr, "04") {
		return models.Keymanage{}, errors.New("invalid uA format")
	}

	ctx := gen.ctxPool.Get().(*ssclWorkerCtx)
	defer gen.ctxPool.Put(ctx)

	ctx.hasher.Reset()
	ctx.buffer = ctx.buffer[:0]

	if _, ok := ctx.ux.SetString(uAStr[2:66], 16); !ok {
		return models.Keymanage{}, errors.New("invalid uA hex")
	}
	if _, ok := ctx.uy.SetString(uAStr[66:130], 16); !ok {
		return models.Keymanage{}, errors.New("invalid uA hex")
	}
	if !gen.curve.IsOnCurve(ctx.ux, ctx.uy) {
		return models.Keymanage{}, errors.New("uA is not on curve")
	}

	ctx.ux.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)
	ctx.uy.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)
	io.WriteString(ctx.hasher, identityData)

	ctx.buffer = ctx.hasher.Sum(ctx.buffer)
	ctx.mx.SetBytes(ctx.buffer)
	ctx.mx.Mod(ctx.mx, gen.n)

	computeShareInternal(gen.coefficients, ctx.mx, gen.n, ctx)

	ctx.buffer = ctx.buffer[:0]
	ctx.buffer = append(ctx.buffer, `{"SSCLKey":"04`...)

	ctx.mx.FillBytes(ctx.temp32)
	startIdx := len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.my.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","SSCLEA":"`...)
	gen.coefficients[0].FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","SSCLDomain":"`...)
	ctx.buffer = append(ctx.buffer, keyDomain...)

	// ⚠️ 历史上这里会在 key_use == "演示计算" / "前置构建" 时把 SSCL 的份额中间量
	// kgcMx 一并写进 key_value。它与 SM2 侧同源的 kgcRandomW/kgcLambda 一起，
	// 构成一条可从只读接口反推 KGC 主私钥 ms 的泄露路径。
	// 现已彻底移除；界面若仍需展示计算过程，必须改用不含秘密的演示数据。
	ctx.buffer = append(ctx.buffer, `"}`...)

	return models.Keymanage{
		KeyValue:  string(ctx.buffer),
		UA:        uAStr,
		KeyDomain: keyDomain,
	}, nil
}

func computeShareInternal(coefficients []*big.Int, x *big.Int, n *big.Int, ctx *ssclWorkerCtx) *big.Int {
	ctx.tempPow.SetInt64(1)
	ctx.my.SetInt64(0)
	for _, coeff := range coefficients {
		ctx.tempMul.Mul(coeff, ctx.tempPow)
		ctx.my.Add(ctx.my, ctx.tempMul)
		ctx.my.Mod(ctx.my, n)
		ctx.tempPow.Mul(ctx.tempPow, x)
		ctx.tempPow.Mod(ctx.tempPow, n)
	}
	return ctx.my
}

func makePointStr(x, y *big.Int) string {
	buf := make([]byte, 130)
	copy(buf[0:2], "04")

	temp := make([]byte, 32)

	x.FillBytes(temp)
	hex.Encode(buf[2:66], temp)

	y.FillBytes(temp)
	hex.Encode(buf[66:130], temp)

	return string(buf)
}

func (gen *SSCLGenerator) GetComParam() map[string]interface{} {
	return map[string]interface{}{
		"n":       gen.n,
		"G":       gen.gStr,
		"PPub":    gen.pPubStr,
		"xIndexs": gen.xIndexs,
		"yIndexs": gen.yIndexs,
	}
}
