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

	hasher  hash.Hash
	buffer  []byte
	temp32  []byte
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

	msHex := "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"
	ms, _ := new(big.Int).SetString(msHex, 16)

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

	// Appending intermediate variables for UI demystification IF needed for demo
	if keyUse == "演示计算" || keyUse == "前置构建" {
		ctx.buffer = append(ctx.buffer, `","kgcRandomW":"`...)
		ctx.w.FillBytes(ctx.temp32)
		startIdx = len(ctx.buffer)
		ctx.buffer = append(ctx.buffer, zeros64[:]...)
		hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

		ctx.buffer = append(ctx.buffer, `","kgcLambda":"`...)
		ctx.lambda.FillBytes(ctx.temp32)
		startIdx = len(ctx.buffer)
		ctx.buffer = append(ctx.buffer, zeros64[:]...)
		hex.Encode(ctx.buffer[startIdx:], ctx.temp32)
	}

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

