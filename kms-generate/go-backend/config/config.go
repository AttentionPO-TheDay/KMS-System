package config

import (
	"encoding/hex"
	"os"
	"strconv"
	"strings"
)

// Kafka 配置
var (
	KafkaAddr  = getEnv("KAFKA_ADDR", "kafka:9092")
	KafkaTopic = getEnv("KAFKA_TOPIC", "key_generate_log")
)

// Server 配置
var (
	ServerPort      = getEnv("SERVER_PORT", "8081")
	JavaBackendBase = getEnv("JAVA_BACKEND_BASE", "http://localhost:9081")
	DemoBackendBase = getEnv("DEMO_BACKEND_BASE", "http://localhost:8000/api/pqkds")
)

// 内部鉴权配置
// Java 后端调用 Go 时需在 Header 携带：X-Internal-Token: <InternalToken>
// 只要 Token 匹配，Go 便信任该请求已由 Java 完成鉴权。
//
// 必须由环境变量 INTERNAL_TOKEN 注入，无默认值：历史默认值为公开值
// "kms-generate-internal-secret-2026"，泄露后可触达生成/更新/回收接口。
var (
	InternalToken = getEnvRequired("INTERNAL_TOKEN")
)

// App 配置
var (
	AppName = "key-service-generate"
)

// KGC（密钥生成中心）主私钥配置
//
// 该值原为硬编码常量，是无证书方案中唯一的秘密：一旦公开，任何持有源码者
// 都能为任意身份伪造部分私钥，从而架空整个无证书安全模型。
//
// 重要：本服务（generate-go）才是**真正生成 SM2/SSCL 部分私钥**的地方。
// 历史上有两个叠加的问题：
//   1. 它在 docker-compose 里**没有被注入 KGC_MASTER_SECRET**，
//      因此永远走下面的演示默认值分支；
//   2. 该默认值还写在源码里，并且能经 `演示计算` 请求间接泄露中间量反推出来。
// 现在：compose 已补齐注入，且这里**去掉静默回退**——缺失或仍是演示值即 panic。
//
// 轮换影响：该值同时经 CalculatePA 用于重算上链公钥，也用于派生 SSCL 域份额，
// 变更会使链上已存证公钥与库内数据不一致、历史存证无法校验。
// 轮换必须连同存量密钥的重新登记一起做，而非只改这一个变量。
// 详见 doc/kms-restructure-plan.md 的 R17。
var (
	KgcMasterSecret = getKgcMasterSecret()
)

// DemoKgcMasterSecret 是公开的演示用主私钥。
//
// 它已**不可用于运行**：配置成这个值会直接 panic。保留常量只是为了在报错信息里
// 认出"你用的还是那个公开值"，以及给审计/迁移脚本做比对。
const DemoKgcMasterSecret = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"

// UsingDemoKgcMasterSecret 表示当前是否仍在使用公开的演示默认值。
// 正常运行时**恒为 false**（否则进程已 panic 退出）。
func UsingDemoKgcMasterSecret() bool {
	return KgcMasterSecret == DemoKgcMasterSecret
}

// getKgcMasterSecret 读取并校验 KGC 主私钥；不满足要求时立即 panic。
//
// 与 getEnvRequired 的取舍一致：宁可启动失败，也不要带着公开秘密对外服务。
func getKgcMasterSecret() string {
	val := os.Getenv("KGC_MASTER_SECRET")
	if val == "" {
		panic("必填环境变量缺失: KGC_MASTER_SECRET（KGC 主私钥）。" +
			"该值是无证书方案里唯一的秘密，缺失时不能再回退到公开的演示值——那等于把秘密公开。" +
			"请注入一把真实随机值（openssl rand -hex 32）后重启，参见 kms-ops/.env.example。")
	}
	val = strings.TrimSpace(val)
	if strings.EqualFold(val, DemoKgcMasterSecret) {
		panic("KGC_MASTER_SECRET 仍是**公开的演示默认值**。" +
			"该值存在于源码与历史文档中，且可被只读接口间接反推，" +
			"任何拿到它的人都能为任意身份伪造部分私钥。" +
			"请轮换为真实随机值（openssl rand -hex 32）后重启；" +
			"注意轮换会改变链上公钥与 SSCL 份额的派生结果，存量密钥需重新登记" +
			"（见 doc/kms-restructure-plan.md R17）。")
	}
	if len(val) != 64 {
		panic("KGC_MASTER_SECRET 格式非法：应为 64 位十六进制（32 字节），" +
			"实际长度为 " + strconv.Itoa(len(val)) + "。生成示例：openssl rand -hex 32。")
	}
	if _, err := hex.DecodeString(val); err != nil {
		panic("KGC_MASTER_SECRET 不是合法的十六进制字符串: " + err.Error() +
			"。生成示例：openssl rand -hex 32。")
	}
	return strings.ToUpper(val)
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// getEnvRequired 读取必填环境变量；缺失时立即 panic，
// 避免以不安全的默认值（如公开的内部 Token / 演示密钥）继续启动。
func getEnvRequired(key string) string {
	val := os.Getenv(key)
	if val == "" {
		panic("必填环境变量缺失: " + key + "。请参照 kms-ops/.env.example 配置后再启动。")
	}
	return val
}
