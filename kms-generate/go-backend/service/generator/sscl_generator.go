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

	msHex := "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"
	ms, _ := new(big.Int).SetString(msHex, 16)

	xPPub, yPPub := c.ScalarMult(gx, gy, ms.Bytes())

	gStr := makePointStr(gx, gy)
	pPubStr := makePointStr(xPPub, yPPub)

	t := 10
	coefficients := make([]*big.Int, t+1)

	wa := mustRand(n)
	eA := new(big.Int).Mul(ms, wa)
	eA.Mod(eA, n)
	coefficients[0] = eA

	for i := 1; i <= t; i++ {
		coefficients[i] = mustRand(n)
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
		xIndexs[i] = mustRand(n)
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

func (gen *SSCLGenerator) GenPartialKey(identityData string, uAStr string, keyDomain string) (models.Keymanage, error) {
	if len(uAStr) != 130 || !strings.HasPrefix(uAStr, "04") {
		return models.Keymanage{}, errors.New("invalid uA format")
	}

	ctx := gen.ctxPool.Get().(*ssclWorkerCtx)
	defer gen.ctxPool.Put(ctx)

	ctx.hasher.Reset()
	ctx.buffer = ctx.buffer[:0]

	ctx.ux.SetString(uAStr[2:66], 16)
	ctx.uy.SetString(uAStr[66:130], 16)
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
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.my.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","SSCLEA":"`...)
	gen.coefficients[0].FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	ctx.buffer = append(ctx.buffer, `","SSCLDomain":"`...)
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
