package generator

import (
	"encoding/hex"
	"math/big"
	"strings"
	"testing"

	"github.com/tjfoc/gmsm/sm2"
)

// =============================================================================
// SSCL 域参数确定性测试
// -----------------------------------------------------------------------------
// 修复前：newSSCLGenerator() 用 mustRand(n) 随机抽 wa、coefficients[1..T]、xIndexs，
// 于是每次构造（= 每次进程重启）得到一套不同的"公开参数"，已签发密钥里存的
// SSCLKey/SSCLEA 随之失配；Java 侧又是另一套独立随机的系数，导致客户端拿到的
// T+1 个插值点根本不在同一条 T 次多项式上。
// 修复后：全部由主私钥 ms 确定性派生（见 sscl_domain_derive.go）。
// 本文件锁定三件事：
//   1. 两次独立构造必须逐位一致；
//   2. 派生标签字符串必须是钉死的常量（改动会静默破坏与 Java 的跨语言一致性）；
//   3. 给定 ms 的已知答案（KAT）—— Java 侧必须能算出同一组数字。
// =============================================================================

// katMsHex 是测试专用的 ms（与 run-tests.ps1 注入的占位值一致）。
// KAT 值来自 Go 与 Java 双侧比对 + Node/OpenSSL SM3 第三方独立复算，
// 因此它可以当作跨语言契约的锚点：任何一侧改了标签、字节序或拒绝条件，
// 这个测试都会红。
const katMsHex = "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF"

func mustHexInt(t *testing.T, value string) *big.Int {
	t.Helper()
	v, ok := new(big.Int).SetString(value, 16)
	if !ok {
		t.Fatalf("无法解析十六进制常量: %s", value)
	}
	return v
}

func testHex64(v *big.Int) string {
	b := make([]byte, 32)
	v.FillBytes(b)
	return hex.EncodeToString(b)
}

// evalShare 用生产代码 evaluate 多项式，并复制返回值（computeShareInternal 返回的是 ctx 内部缓冲的别名）。
func evalShare(coefficients []*big.Int, x, n *big.Int) *big.Int {
	ctx := &ssclWorkerCtx{
		tempPow: new(big.Int),
		tempMul: new(big.Int),
		tempSum: new(big.Int),
		my:      new(big.Int),
	}
	return new(big.Int).Set(computeShareInternal(coefficients, x, n, ctx))
}

// TestSSCLDomainParamsAreDeterministic 断言两次独立构造的生成器产生完全一致的域参数。
func TestSSCLDomainParamsAreDeterministic(t *testing.T) {
	first := newSSCLGenerator()
	second := newSSCLGenerator()

	if first.gStr != second.gStr {
		t.Fatalf("G 不一致:\n  first =%s\n  second=%s", first.gStr, second.gStr)
	}
	if first.pPubStr != second.pPubStr {
		t.Fatalf("PPub 不一致:\n  first =%s\n  second=%s", first.pPubStr, second.pPubStr)
	}
	if first.n.Cmp(second.n) != 0 || first.ms.Cmp(second.ms) != 0 {
		t.Fatal("曲线阶 n 或主私钥 ms 不一致")
	}
	if len(first.coefficients) != len(second.coefficients) {
		t.Fatalf("系数个数不一致: %d vs %d", len(first.coefficients), len(second.coefficients))
	}
	for i := range first.coefficients {
		if first.coefficients[i].Cmp(second.coefficients[i]) != 0 {
			t.Fatalf("coef[%d] 不一致:\n  first =%s\n  second=%s",
				i, first.coefficients[i].Text(16), second.coefficients[i].Text(16))
		}
	}
	if len(first.xIndexs) != first.t || len(first.yIndexs) != first.t {
		t.Fatalf("评测点个数应为 T=%d，实际 x=%d y=%d", first.t, len(first.xIndexs), len(first.yIndexs))
	}
	for i := range first.xIndexs {
		if first.xIndexs[i].Cmp(second.xIndexs[i]) != 0 {
			t.Fatalf("x[%d] 不一致:\n  first =%s\n  second=%s",
				i+1, first.xIndexs[i].Text(16), second.xIndexs[i].Text(16))
		}
		if first.yIndexs[i].Cmp(second.yIndexs[i]) != 0 {
			t.Fatalf("y[%d] 不一致:\n  first =%s\n  second=%s",
				i+1, first.yIndexs[i].Text(16), second.yIndexs[i].Text(16))
		}
	}

	// 单例路径（GetSSCLGenerator，sync.Once）也必须给出同一套参数。
	singleton := GetSSCLGenerator()
	if singleton.pPubStr != first.pPubStr {
		t.Fatalf("单例 PPub 与独立构造不一致: %s vs %s", singleton.pPubStr, first.pPubStr)
	}
	for i := range first.coefficients {
		if singleton.coefficients[i].Cmp(first.coefficients[i]) != 0 {
			t.Fatalf("单例 coef[%d] 与独立构造不一致", i)
		}
	}
	for i := range first.xIndexs {
		if singleton.xIndexs[i].Cmp(first.xIndexs[i]) != 0 {
			t.Fatalf("单例 x[%d] 与独立构造不一致", i+1)
		}
	}
}

// TestSSCLDomainDeriveIsRepeatable 直接对派生函数做纯函数性校验（不依赖 config）。
func TestSSCLDomainDeriveIsRepeatable(t *testing.T) {
	ms := mustHexInt(t, katMsHex)
	n := sm2.P256Sm2().Params().N

	labels := []string{
		domainLabelWA(),
		domainLabelCoef(1),
		domainLabelCoef(10),
		domainLabelX(1, 0),
		domainLabelX(10, 3),
	}
	for _, label := range labels {
		a := deriveDomainScalar(ms, label, n)
		b := deriveDomainScalar(ms, label, n)
		if a.Cmp(b) != 0 {
			t.Fatalf("label=%s 两次派生结果不同: %s vs %s", label, a.Text(16), b.Text(16))
		}
		if a.Sign() <= 0 || a.Cmp(n) >= 0 {
			t.Fatalf("label=%s 派生值超出 [1, n): %s", label, a.Text(16))
		}
	}
}

// TestSSCLDomainLabelsArePinned 钉死标签字符串：labels 是跨语言线上的契约，
// 一旦改动，Java 侧（SsclKeyGenerator.java）必须同步改，否则两侧多项式不再相同。
func TestSSCLDomainLabelsArePinned(t *testing.T) {
	cases := map[string]string{
		domainLabelWA():      "KMS-SSCL-DOMAIN-v1|wa",
		domainLabelCoef(1):   "KMS-SSCL-DOMAIN-v1|coef|1",
		domainLabelCoef(10):  "KMS-SSCL-DOMAIN-v1|coef|10",
		domainLabelX(1, 0):   "KMS-SSCL-DOMAIN-v1|x|1|0",
		domainLabelX(10, 7):  "KMS-SSCL-DOMAIN-v1|x|10|7",
		domainLabelX(2, 255): "KMS-SSCL-DOMAIN-v1|x|2|255",
	}
	for got, want := range cases {
		if got != want {
			t.Fatalf("派生标签被改动: got=%q want=%q（改动会破坏与 Java 的跨语言一致性）", got, want)
		}
	}
}

// lagrangeAtZero 复刻浏览器客户端的 getSecret
// （kms-user/front/src/views/generate/GenerateView.vue）：在 x=0 处对给定点集做插值。
func lagrangeAtZero(t *testing.T, xs, ys []*big.Int, n *big.Int) *big.Int {
	t.Helper()
	secret := new(big.Int)
	for i := range xs {
		num := big.NewInt(1)
		den := big.NewInt(1)
		for j := range xs {
			if i == j {
				continue
			}
			num.Mul(num, new(big.Int).Neg(xs[j]))
			num.Mod(num, n)
			diff := new(big.Int).Sub(xs[i], xs[j])
			diff.Mod(diff, n)
			den.Mul(den, diff)
			den.Mod(den, n)
		}
		inv := new(big.Int).ModInverse(den, n)
		if inv == nil {
			t.Fatalf("插值分母不可逆：x[%d] 与其它点重合", i)
		}
		term := new(big.Int).Mul(ys[i], num)
		term.Mod(term, n)
		term.Mul(term, inv)
		term.Mod(term, n)
		secret.Add(secret, term)
		secret.Mod(secret, n)
	}
	return secret
}

// TestSSCLClientInterpolationRecoversDomainSecret 复刻客户端还原域秘密的完整路径：
// 取 /comparam 发布的 T 个点 (xIndexs[i], yIndexs[i])，加上自己密钥里的 (mx, my)，
// 共 T+1 个点，在 x=0 处插值必须恰好还原常数项 coef[0]（即 SSCLEA）。
//
// 这正是修复前的两个症状会破坏的性质：
//   - 重启后 xIndexs/yIndexs 换成另一条多项式上的点 → 插值出垃圾；
//   - Java 用自己随机的系数算 my → 11 个点不共线 → 插值出垃圾。
func TestSSCLClientInterpolationRecoversDomainSecret(t *testing.T) {
	gen := newSSCLGenerator()

	// 用基点 G 作为 uA（必然在曲线上），其余流程与真实调用完全一致。
	res, err := gen.GenPartialKey("alice", gen.gStr, "test-domain", "")
	if err != nil {
		t.Fatalf("GenPartialKey 返回错误: %v", err)
	}

	const keyTag = `"SSCLKey":"`
	idx := strings.Index(res.KeyValue, keyTag)
	if idx < 0 {
		t.Fatalf("响应里没有 SSCLKey: %s", res.KeyValue)
	}
	share := res.KeyValue[idx+len(keyTag):]
	if len(share) < 130 || !strings.HasPrefix(share, "04") {
		t.Fatalf("SSCLKey 格式非法: %s", share)
	}
	mx, ok := new(big.Int).SetString(share[2:66], 16)
	if !ok {
		t.Fatalf("mx 非法: %s", share[2:66])
	}
	my, ok := new(big.Int).SetString(share[66:130], 16)
	if !ok {
		t.Fatalf("my 非法: %s", share[66:130])
	}

	xs := make([]*big.Int, 0, gen.t+1)
	ys := make([]*big.Int, 0, gen.t+1)
	for i := 0; i < gen.t; i++ {
		xs = append(xs, gen.xIndexs[i])
		ys = append(ys, gen.yIndexs[i])
	}
	xs = append(xs, mx)
	ys = append(ys, my)

	secret := lagrangeAtZero(t, xs, ys, gen.n)
	if secret.Cmp(gen.coefficients[0]) != 0 {
		t.Fatalf("客户端插值未还原常数项:\n  插值得到=%s\n  coef[0] =%s",
			secret.Text(16), gen.coefficients[0].Text(16))
	}
	// SSCLEA 字段必须就是同一个常数项，客户端的 dA = 插值值 * mx mod n 才成立。
	if !strings.Contains(res.KeyValue, `"SSCLEA":"`+testHex64(gen.coefficients[0])+`"`) {
		t.Fatalf("SSCLEA 与常数项不一致: %s", res.KeyValue)
	}
}

// TestSSCLDomainKnownAnswer 用固定 ms 锁定已知答案。
// 这些数字同时由 Java 侧 SsclKeyGenerator 派生并用 Node/OpenSSL 的 SM3 独立复算过，
// 是"Go 与 Java 必须算出同一组域参数"这条契约的可执行版本。
func TestSSCLDomainKnownAnswer(t *testing.T) {
	ms := mustHexInt(t, katMsHex)
	c := sm2.P256Sm2()
	n := c.Params().N

	wa := deriveDomainScalar(ms, domainLabelWA(), n)
	if got, want := testHex64(wa), "5264c47d3af01fb476874fc7b3c94cf9529ff5210dd347b766e48f7b37806a83"; got != want {
		t.Fatalf("wa 不符合已知答案:\n  got =%s\n  want=%s", got, want)
	}

	coefficients := make([]*big.Int, 11)
	coefficients[0] = new(big.Int).Mul(ms, wa)
	coefficients[0].Mod(coefficients[0], n)
	for i := 1; i <= 10; i++ {
		coefficients[i] = deriveDomainScalar(ms, domainLabelCoef(i), n)
	}

	coefKAT := map[int]string{
		0:  "bae16536c31ecffaa1192b60cf97e2f9467fe93da338b231af5f7ed1ce5190f0",
		1:  "0bd821ae10d557fd05c8f110655b8e1b13a1ee7758a0dc1a1293df29c262acaa",
		10: "7f1e3ac7123357bb044b607abd85589b5551af82a3947f884e3bc5bc77352378",
	}
	for i, want := range coefKAT {
		if got := testHex64(coefficients[i]); got != want {
			t.Fatalf("coef[%d] 不符合已知答案:\n  got =%s\n  want=%s", i, got, want)
		}
	}
	// coef[0] 必须保持 ms*wa mod n（SSCLEA = coef[0] 依赖它）。
	expectEA := new(big.Int).Mul(ms, wa)
	expectEA.Mod(expectEA, n)
	if coefficients[0].Cmp(expectEA) != 0 {
		t.Fatal("coef[0] 必须等于 ms*wa mod n")
	}

	// x[1..10] 与 y[1..10]：按"首个不碰撞尝试胜出"的规则顺序派生。
	accepted := make([]*big.Int, 0, 10)
	for i := 1; i <= 10; i++ {
		accepted = append(accepted, deriveDomainXIndex(ms, i, n, accepted))
	}
	for i, x := range accepted {
		for j := 0; j < i; j++ {
			if accepted[j].Cmp(x) == 0 {
				t.Fatalf("x[%d] 与 x[%d] 碰撞", j+1, i+1)
			}
		}
	}
	if got, want := testHex64(accepted[0]), "ea0fedf7c95d031968b9f38ac8c44081b2395f6b4defbb5b26ad4b58e3f576ad"; got != want {
		t.Fatalf("x[1] 不符合已知答案:\n  got =%s\n  want=%s", got, want)
	}
	if got, want := testHex64(accepted[9]), "b196cb6ed8b870eea8a51a5d1c6af496983eb0a6bcfffe387c7c34c2c478ac11"; got != want {
		t.Fatalf("x[10] 不符合已知答案:\n  got =%s\n  want=%s", got, want)
	}
	if got, want := testHex64(evalShare(coefficients, accepted[0], n)), "9652804ade91ec3f21b7f21aa7fe94196eb853d81ceb4d152183e6b260a3188a"; got != want {
		t.Fatalf("y[1] 不符合已知答案:\n  got =%s\n  want=%s", got, want)
	}
	if got, want := testHex64(evalShare(coefficients, accepted[9], n)), "a757fecc5ec6a7f12a7fdd1a29185c0522c0924fa149dcfb5addcd5fb349f91f"; got != want {
		t.Fatalf("y[10] 不符合已知答案:\n  got =%s\n  want=%s", got, want)
	}

	// PPub = ms*G 未受本次修复影响，必须保持原值。
	gx, gy := c.Params().Gx, c.Params().Gy
	ppubX, ppubY := c.ScalarMult(gx, gy, ms.Bytes())
	ppub := makePointStr(ppubX, ppubY)
	wantPPub := "04344081b80805540a38d71d721bd072d8957eae15aeb852e72086ab4c5962b89b5bb8628b9d9c4edd30f341a5a25886c063cff46dc04c7e68f2efb3b58830e0f3"
	if ppub != wantPPub {
		t.Fatalf("PPub 不符合已知答案:\n  got =%s\n  want=%s", ppub, wantPPub)
	}
}
