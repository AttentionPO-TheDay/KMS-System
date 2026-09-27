package generator

import (
	"crypto/elliptic"
	"crypto/rand"
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

type ECCGenerator struct {
	curve            elliptic.Curve
	n                *big.Int
	ms               *big.Int
	staticHashSuffix []byte
	ctxPool          sync.Pool
}

type eccWorkerCtx struct {
	x      *big.Int
	y      *big.Int
	w      *big.Int
	lambda *big.Int
	temp   *big.Int
	tA     *big.Int

	hasher    hash.Hash
	buffer    []byte
	temp32    []byte
	temp32Arr [32]byte
}

var zeros64 [64]byte

var (
	globalECCGen *ECCGenerator
	once         sync.Once
)

func GetECCGenerator() *ECCGenerator {
	once.Do(func() {
		globalECCGen = newECCGenerator()
	})
	return globalECCGen
}

func newECCGenerator() *ECCGenerator {
	c := sm2.P256Sm2()
	n := c.Params().N

	// 主私钥来自统一配置源（KGC_MASTER_SECRET），不再硬编码。
	ms, _ := new(big.Int).SetString(config.KgcMasterSecret, 16)

	gx, gy := c.Params().Gx, c.Params().Gy
	xPPub, yPPub := c.ScalarMult(gx, gy, ms.Bytes())

	a, _ := new(big.Int).SetString("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC", 16)
	b := c.Params().B

	suffixBuf := make([]byte, 0, 32*6)
	suffixBuf = append(suffixBuf, initTo32(a)...)
	suffixBuf = append(suffixBuf, initTo32(b)...)
	suffixBuf = append(suffixBuf, initTo32(gx)...)
	suffixBuf = append(suffixBuf, initTo32(gy)...)
	suffixBuf = append(suffixBuf, initTo32(xPPub)...)
	suffixBuf = append(suffixBuf, initTo32(yPPub)...)

	gen := &ECCGenerator{
		curve:            c,
		n:                n,
		ms:               ms,
		staticHashSuffix: suffixBuf,
		ctxPool: sync.Pool{
			New: func() interface{} {
				ctx := &eccWorkerCtx{
					x:      new(big.Int),
					y:      new(big.Int),
					w:      new(big.Int),
					lambda: new(big.Int),
					temp:   new(big.Int),
					tA:     new(big.Int),
					hasher: sm3.New(),
					buffer: make([]byte, 0, 1024),
				}
				ctx.temp32 = ctx.temp32Arr[:]
				return ctx
			},
		},
	}
	return gen
}

func (gen *ECCGenerator) GenPartialKey(identityData string, uAStr string, keyUse string) (models.Keymanage, error) {
	if len(uAStr) != 130 || !strings.HasPrefix(uAStr, "04") {
		return models.Keymanage{}, errors.New("invalid uA format")
	}

	ctx := gen.ctxPool.Get().(*eccWorkerCtx)
	defer gen.ctxPool.Put(ctx)

	ctx.buffer = ctx.buffer[:0]
	ctx.hasher.Reset()

	if _, ok := ctx.x.SetString(uAStr[2:66], 16); !ok {
		return models.Keymanage{}, errors.New("invalid uA hex")
	}
	if _, ok := ctx.y.SetString(uAStr[66:130], 16); !ok {
		return models.Keymanage{}, errors.New("invalid uA hex")
	}

	if !gen.curve.IsOnCurve(ctx.x, ctx.y) {
		return models.Keymanage{}, errors.New("uA is not on curve")
	}

	entlen := uint16(len(identityData) * 8)
	ctx.buffer = append(ctx.buffer, byte(entlen>>8), byte(entlen))
	ctx.hasher.Write(ctx.buffer)
	ctx.buffer = ctx.buffer[:0]

	io.WriteString(ctx.hasher, identityData)
	ctx.hasher.Write(gen.staticHashSuffix)

	ctx.buffer = ctx.hasher.Sum(ctx.buffer)

	rand.Read(ctx.temp32)
	ctx.w.SetBytes(ctx.temp32)
	ctx.w.Mod(ctx.w, gen.n)

	wx, wy := gen.curve.ScalarBaseMult(ctx.w.Bytes())
	wAx, wAy := gen.curve.Add(wx, wy, ctx.x, ctx.y)

	ctx.hasher.Reset()

	wAx.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)

	wAy.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)

	ctx.hasher.Write(ctx.buffer[:32])

	lambdaHash := ctx.hasher.Sum(ctx.buffer[:0])
	ctx.lambda.SetBytes(lambdaHash)
	ctx.lambda.Mod(ctx.lambda, gen.n)

	ctx.temp.Mul(ctx.lambda, gen.ms)
	ctx.tA.Add(ctx.temp, ctx.w)
	ctx.tA.Mod(ctx.tA, gen.n)

	ctx.buffer = ctx.buffer[:0]

	ctx.buffer = append(ctx.buffer, `{"partialKey":"`...)

	ctx.tA.FillBytes(ctx.temp32)
	startIdx := len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","finalPublicKey":"04`...)

	wAx.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	wAy.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, zeros64[:]...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	// ⚠️ 历史上这里会在 key_use == "演示计算" / "前置构建" 时把 KGC 中间量
	// kgcRandomW（KGC 随机数 w）与 kgcLambda（SM3 派生标量 λ）一并写进 key_value。
	//
	// 那是**一条可反推主私钥的泄露路径**：t_A = w + λ·ms，于是
	//     ms = (t_A − w) · λ⁻¹
	// 任何人都能用一个只读的 /PARTIAL_KEY 调用（带 key_use=演示计算）拿到 w 与 λ，
	// 从而解出 KGC 主私钥 ms —— 而 ms 是无证书方案里唯一的秘密。
	// 泄露同时发生在两处：HTTP 响应体，以及随后落库的 key_value。
	//
	// 现已彻底移除该分支。界面上的"计算过程可视化"若仍需展示中间量，
	// 必须改用**不含秘密**的演示数据，不能由真实 KGC 现场计算。
	ctx.buffer = append(ctx.buffer, `"}`...)

	return models.Keymanage{
		KeyValue: string(ctx.buffer),
		UA:       uAStr,
	}, nil
}

func initTo32(i *big.Int) []byte {
	b := i.Bytes()
	if len(b) == 32 {
		return b
	}
	res := make([]byte, 32)
	if len(b) > 32 {
		copy(res, b[len(b)-32:])
	} else {
		copy(res[32-len(b):], b)
	}
	return res
}
