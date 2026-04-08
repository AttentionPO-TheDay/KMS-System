package generator

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"hash"
	"io"
	"math/big"
	"strings"
	"sync"

	"key-service/models" // 确保路径正确

	"github.com/tjfoc/gmsm/sm2"
	"github.com/tjfoc/gmsm/sm3"
)

// SSCLGenerator 对应 Java 的 SSCLGenerator 类
type SSCLGenerator struct {
	n            *big.Int
	ms           *big.Int   // 主密钥
	coefficients []*big.Int // 多项式系数 (t+1 个)
	t            int        // 阈值

	// --- 预计算的静态公共参数 (04开头 Hex 字符串) ---
	gStr    string // 基点 G 的 Hex 字符串 (04+x+y)
	pPubStr string // 主公钥 PPub 的 Hex 字符串 (04+x+y)
	// -------------------------------------------

	// 预计算的共享点 (用于 ComParam)
	xIndexs []*big.Int
	yIndexs []*big.Int

	// 对象池
	ctxPool sync.Pool
}

// ssclWorkerCtx 工作上下文
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

// GetSSCLGenerator 获取单例
func GetSSCLGenerator() *SSCLGenerator {
	ssclOnce.Do(func() {
		globalSSCLGen = newSSCLGenerator()
	})
	return globalSSCLGen
}

func newSSCLGenerator() *SSCLGenerator {
	// 1. 初始化曲线参数
	c := sm2.P256Sm2()
	n := c.Params().N
	gx, gy := c.Params().Gx, c.Params().Gy

	// 2. 初始化主密钥 MS
	msHex := "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"
	ms, _ := new(big.Int).SetString(msHex, 16)

	// --- 预计算 G 和 PPub 的 Hex 字符串 ---
	// 计算 PPub = [ms]G
	xPPub, yPPub := c.ScalarMult(gx, gy, ms.Bytes())

	// 格式化为 04 + Hex(x) + Hex(y)
	// 因为只运行一次，这里直接生成 string 存起来
	gStr := makePointStr(gx, gy)
	pPubStr := makePointStr(xPPub, yPPub)
	// ------------------------------------

	// 3. 初始化多项式系数
	t := 10
	coefficients := make([]*big.Int, t+1)

	wa := mustRand(n)
	eA := new(big.Int).Mul(ms, wa)
	eA.Mod(eA, n)
	coefficients[0] = eA

	for i := 1; i <= t; i++ {
		coefficients[i] = mustRand(n)
	}

	// 4. 初始化共享点
	xIndexs := make([]*big.Int, t)
	yIndexs := make([]*big.Int, t)

	tempCtx := &ssclWorkerCtx{
		tempPow: new(big.Int),
		tempMul: new(big.Int),
		tempSum: new(big.Int),
		my:      new(big.Int),
	}

	for i := 0; i < t; i++ {
		xIndexs[i] = mustRand(n)
		yIndexs[i] = computeShareInternal(coefficients, xIndexs[i], n, tempCtx)
		yIndexs[i] = new(big.Int).Set(yIndexs[i])
	}

	gen := &SSCLGenerator{
		n:            n,
		ms:           ms,
		coefficients: coefficients,
		t:            t,
		// 存储预计算好的字符串
		gStr:    gStr,
		pPubStr: pPubStr,

		xIndexs: xIndexs,
		yIndexs: yIndexs,
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

// GenPartialKey 核心业务方法
func (gen *SSCLGenerator) GenPartialKey(identityData string, uAStr string, keyDomain string) (models.Keymanage, error) {
	// 0. 校验
	if len(uAStr) != 130 || !strings.HasPrefix(uAStr, "04") {
		return models.Keymanage{}, errors.New("invalid uA format")
	}

	// 1. 获取上下文
	ctx := gen.ctxPool.Get().(*ssclWorkerCtx)
	defer gen.ctxPool.Put(ctx)

	ctx.hasher.Reset()
	ctx.buffer = ctx.buffer[:0]

	// 2. 解析 uA
	ctx.ux.SetString(uAStr[2:66], 16)
	ctx.uy.SetString(uAStr[66:130], 16)

	// 3. 计算 Hash
	ctx.ux.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)
	ctx.uy.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)
	io.WriteString(ctx.hasher, identityData)

	// 4. 计算 m
	ctx.buffer = ctx.hasher.Sum(ctx.buffer)
	ctx.mx.SetBytes(ctx.buffer)
	ctx.mx.Mod(ctx.mx, gen.n)

	// 5. 计算 M
	computeShareInternal(gen.coefficients, ctx.mx, gen.n, ctx)

	// 6. 构造 JSON
	ctx.buffer = ctx.buffer[:0]
	ctx.buffer = append(ctx.buffer, `{"SSCLKey":"04`...)

	ctx.mx.FillBytes(ctx.temp32)
	startIdx := len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.my.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","SSCLDomian":"`...)
	ctx.buffer = append(ctx.buffer, keyDomain...)
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

func mustRand(n *big.Int) *big.Int {
	b := make([]byte, 32)
	rand.Read(b)
	r := new(big.Int).SetBytes(b)
	r.Mod(r, n)
	return r
}

// makePointStr 辅助函数：将坐标转换为 04+Hex(x)+Hex(y) 格式字符串
// 仅在初始化时调用，不需要像 GenPartialKey 那样极致优化
func makePointStr(x, y *big.Int) string {
	buf := make([]byte, 130)
	copy(buf[0:2], "04")

	temp := make([]byte, 32)

	// 处理 X
	// FillBytes 保证补齐 32 字节
	x.FillBytes(temp)
	hex.Encode(buf[2:66], temp)

	// 处理 Y
	y.FillBytes(temp)
	hex.Encode(buf[66:130], temp)

	return string(buf)
}

// GetComParam 导出公共参数
func (gen *SSCLGenerator) GetComParam() map[string]interface{} {
	return map[string]interface{}{
		"n": gen.n,
		// 直接返回预计算好的 04 开头的字符串
		"G":    gen.gStr,
		"PPub": gen.pPubStr,
		// 秘密共享点 (如果这些也需要 Hex 格式，也可以仿照上面处理，目前保持 BigInt 数组)
		"xIndexs": gen.xIndexs,
		"yIndexs": gen.yIndexs,
	}
}
