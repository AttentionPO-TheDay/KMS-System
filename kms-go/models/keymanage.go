// models/keymanage.go
package models

// 对应 Java 的 UserIdentity.java
type UserIdentity struct {
	Version      string `json:"version,omitempty"`
	IdentityType string `json:"identity_type,omitempty"`
	Alias        string `json:"alias,omitempty"`
	IdentityData string `json:"identity_data"` // 核心字段：用户标识数据
	Serial       string `json:"serial,omitempty"`
	ValidStart   string `json:"valid_start,omitempty"`
	ValidEnd     string `json:"valid_end,omitempty"`
	IDExtensions string `json:"id_extensions,omitempty"`
}

type Keymanage struct {
	KeyID        int64         `json:"key_id,omitempty"`     // 对应 Long keyId
	UserID       int64         `json:"user_id,omitempty"`    // 对应 Long userId
	UserName     string        `json:"user_name"`            // 对应 String userName
	UserIdentity *UserIdentity `json:"user_identity"`        // 对应 UserIdentity 对象
	UA           string        `json:"ua"`                   // 用户的部分公钥 (Hex 字符串)
	EncrytType   string        `json:"encryt_type"`          // 加密算法类型
	EncrytName   string        `json:"encryt_name"`          // 加密算法名称 (SM2/SSCL/AES)
	KeyName      string        `json:"key_name"`             // 密钥名称
	KeyUse       string        `json:"key_use"`              // 密钥用途
	KeyValue     string        `json:"key_value"`            // 密钥值 (JSON 字符串，存储生成的密钥)
	CreTime      string        `json:"cre_time"`             // 创建时间
	UpdTime      string        `json:"upd_time"`             // 更新时间
	AutoUpdate   string        `json:"auto_update"`          // 密钥自动更新状态
	Status       string        `json:"status"`               // 密钥工作状态
	KeyDomain    string        `json:"key_domain,omitempty"` // SSCL密钥的域
}

// 新增：Kafka 消息协议结构
// 这是为了实现“鉴别密码操作延迟到数据库”的关键结构
type KeyEnrollPayload struct {
	// 原始请求数据（用于 Java 端鉴权）
	RawUser     string `json:"raw_user"`
	RawPassword string `json:"raw_password"`

	// Go 端生成好的业务数据
	GeneratedKey Keymanage `json:"generated_key"`

	// 操作类型 (对应 Controller 的 ENROLL_KEY 等)
	ActionType string `json:"action_type"`
}
