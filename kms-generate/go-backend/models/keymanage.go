package models

// UserIdentity 对应 Java 的 UserIdentity.java
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
	KeyID        int64         `json:"key_id,omitempty"`
	UserID       int64         `json:"user_id,omitempty"`
	UserName     string        `json:"user_name"`
	UserIdentity *UserIdentity `json:"user_identity"`
	UA           string        `json:"ua"`
	EncrytType   string        `json:"encryt_type"`
	EncrytName   string        `json:"encryt_name"`
	KeyName      string        `json:"key_name"`
	KeyUse       string        `json:"key_use"`
	KeyValue     string        `json:"key_value"`
	CreTime      string        `json:"cre_time"`
	UpdTime      string        `json:"upd_time"`
	AutoUpdate   string        `json:"auto_update"`
	Status       string        `json:"status"`
	KeyDomain    string        `json:"key_domain,omitempty"`
}

// KeyEnrollPayload Kafka 消息协议结构
type KeyEnrollPayload struct {
	RawUser      string `json:"raw_user"`
	RawPassword  string `json:"raw_password"`
	GeneratedKey Keymanage `json:"generated_key"`
	ActionType   string `json:"action_type"`
}

// EnrollRequest 注册请求
type EnrollRequest struct {
	User       string `json:"user"`
	Password   string `json:"password"`
	EncrytType string `json:"encryt_type"`
	EncrytName string `json:"encryt_name"`
	UA         string `json:"ua"`
	KeyDomain  string `json:"key_domain"`
}