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

	"key-service/models" // 请确保路径正确

	"github.com/tjfoc/gmsm/sm2"
	"github.com/tjfoc/gmsm/sm3"
)

// ECCGenerator 单例且线程安全
type ECCGenerator struct {
	curve            elliptic.Curve
	n                *big.Int
	ms               *big.Int // 主密钥
	staticHashSuffix []byte
	ctxPool          sync.Pool
}

// eccWorkerCtx 工作上下文，包含所有需要复用的内存
type eccWorkerCtx struct {
	// BigInt 对象复用
	x      *big.Int
	y      *big.Int
	w      *big.Int
	lambda *big.Int
	temp   *big.Int
	tA     *big.Int

	// Hasher 复用 (避免每次 sm3.New)
	hasher hash.Hash

	// 内存复用 (避免 make([]byte))
	buffer    []byte   // 用于 JSON 拼接 (2KB)
	temp32    []byte   // 用于存放 32字节 的中间结果 (Slice header reuse)
	temp32Arr [32]byte // 实际的底层数组
}

var (
	globalECCGen *ECCGenerator
	once         sync.Once
)

// GetECCGenerator 获取单例
func GetECCGenerator() *ECCGenerator {
	once.Do(func() {
		globalECCGen = newECCGenerator()
	})
	return globalECCGen
}

func newECCGenerator() *ECCGenerator {
	// 1. 初始化曲线
	c := sm2.P256Sm2()
	n := c.Params().N

	// 2. 初始化主密钥 MS
	msHex := "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"
	ms, _ := new(big.Int).SetString(msHex, 16)

	// 3. 计算 PPub = [ms]G
	gx, gy := c.Params().Gx, c.Params().Gy
	// 忽略 Deprecated 警告，这是 SM2 必须的
	xPPub, yPPub := c.ScalarMult(gx, gy, ms.Bytes())

	// 4. 预计算静态参数
	a, _ := new(big.Int).SetString("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC", 16)
	b := c.Params().B

	// 仅在初始化时使用简单的 helper，不影响运行时性能
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
				// 初始化 Worker Context
				ctx := &eccWorkerCtx{
					x:      new(big.Int),
					y:      new(big.Int),
					w:      new(big.Int),
					lambda: new(big.Int),
					temp:   new(big.Int),
					tA:     new(big.Int),
					hasher: sm3.New(),
					// 预分配 buffer 避免扩容
					buffer: make([]byte, 0, 1024),
				}
				// 设置 temp32 切片指向数组
				ctx.temp32 = ctx.temp32Arr[:]
				return ctx
			},
		},
	}
	return gen
}

// GenPartialKey 极速优化版
func (gen *ECCGenerator) GenPartialKey(identityData string, uAStr string) (models.Keymanage, error) {
	// 0. 参数校验 (快速失败)
	if len(uAStr) != 130 || !strings.HasPrefix(uAStr, "04") {
		return models.Keymanage{}, errors.New("invalid uA format")
	}

	// 1. 获取上下文
	ctx := gen.ctxPool.Get().(*eccWorkerCtx)
	defer gen.ctxPool.Put(ctx)

	// 重置 buffer 长度为 0 (逻辑清空)
	ctx.buffer = ctx.buffer[:0]
	// 重置 hasher
	ctx.hasher.Reset()

	// 2. 解析 uA (HexString -> BigInt)
	// 即使这里分配字符串切片也没关系，因为是指针引用，开销极小
	// 如果追求极致，可用 hex.Decode 到 temp buffer 再 SetBytes，但 SetString 足够快
	ctx.x.SetString(uAStr[2:66], 16)
	ctx.y.SetString(uAStr[66:130], 16)

	if !gen.curve.IsOnCurve(ctx.x, ctx.y) {
		return models.Keymanage{}, errors.New("uA is not on curve")
	}

	// 3. 计算 Hash 1 (hA)
	// 3.1 ENTL_A
	entlen := uint16(len(identityData) * 8)
	// 直接写入 2 字节，避免 slice 分配
	ctx.buffer = append(ctx.buffer, byte(entlen>>8), byte(entlen))
	ctx.hasher.Write(ctx.buffer)
	ctx.buffer = ctx.buffer[:0] // 用完立刻清空 buffer 复用

	// 3.2 ID_A
	// 使用 io.WriteString 避免 string -> []byte 的内存拷贝
	io.WriteString(ctx.hasher, identityData)

	// 3.3 Static Suffix
	ctx.hasher.Write(gen.staticHashSuffix)

	// 计算 hA，结果暂存到 buffer
	// Sum(nil) 会分配新内存，Sum(buf) 会追加到 buf
	// 我们把 hA 结果追加到 buffer 前端
	ctx.buffer = ctx.hasher.Sum(ctx.buffer)
	// 此时 ctx.buffer[0:32] 是 hA 的值

	// 4. 生成随机数 w
	// 直接读入预分配的 temp32，零分配
	rand.Read(ctx.temp32)
	ctx.w.SetBytes(ctx.temp32)
	ctx.w.Mod(ctx.w, gen.n)

	// 5. 计算 wA = [w]G + uA
	// 忽略 Deprecated 警告
	wx, wy := gen.curve.ScalarBaseMult(ctx.w.Bytes())
	wAx, wAy := gen.curve.Add(wx, wy, ctx.x, ctx.y)

	// 6. 计算 Hash 2 (lambda)
	ctx.hasher.Reset()

	// 写入 wAx (32 bytes)
	wAx.FillBytes(ctx.temp32) // 直接填入数组，不产生新 slice
	ctx.hasher.Write(ctx.temp32)

	// 写入 wAy (32 bytes)
	wAy.FillBytes(ctx.temp32)
	ctx.hasher.Write(ctx.temp32)

	// 写入 hA (之前存在 buffer[0:32] 中)
	ctx.hasher.Write(ctx.buffer[:32])

	// 计算 lambda
	// 复用 buffer 的后半部分或者重新利用 temp32?
	// 直接算出 bytes 设置给 BigInt 即可
	lambdaHash := ctx.hasher.Sum(ctx.buffer[:0]) // 借用 buffer 暂存结果，避免分配
	ctx.lambda.SetBytes(lambdaHash)
	ctx.lambda.Mod(ctx.lambda, gen.n)

	// 7. 计算 tA = (w + lambda * ms) mod n
	ctx.temp.Mul(ctx.lambda, gen.ms)
	ctx.tA.Add(ctx.temp, ctx.w)
	ctx.tA.Mod(ctx.tA, gen.n)

	// -------------------------------------------------------
	// 8. 构造 JSON 结果 (零分配核心逻辑)
	// -------------------------------------------------------
	// 目标格式: {"partialKey":"Hex(tA)","finalPublicKey":"04+Hex(wAx)+Hex(wAy)"}

	ctx.buffer = ctx.buffer[:0] // 清空 buffer

	// A. 拼接头部
	ctx.buffer = append(ctx.buffer, `{"partialKey":"`...)

	// B. 拼接 tA (Hex)
	// 先获取 tA 的二进制到 temp32
	ctx.tA.FillBytes(ctx.temp32)
	// 扩容 buffer 64字节
	startIdx := len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	// 将 temp32 编码为 Hex 直接写入 buffer
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	// C. 拼接中间
	ctx.buffer = append(ctx.buffer, `","finalPublicKey":"04`...)

	// D. 拼接 wAx (Hex)
	wAx.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	// E. 拼接 wAy (Hex)
	wAy.FillBytes(ctx.temp32)
	startIdx = len(ctx.buffer)
	ctx.buffer = append(ctx.buffer, make([]byte, 64)...)
	hex.Encode(ctx.buffer[startIdx:], ctx.temp32)

	// F. 拼接尾部
	ctx.buffer = append(ctx.buffer, `"}`...)

	// 最终只分配一次 string 内存
	return models.Keymanage{
		KeyValue: string(ctx.buffer),
		UA:       uAStr,
	}, nil
}

// initTo32 仅用于初始化阶段的辅助函数
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
