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
	KeyID            int64         `json:"key_id,omitempty"`
	UserID           int64         `json:"user_id,omitempty"`
	UserName         string        `json:"user_name"`
	UserIdentity     *UserIdentity `json:"user_identity"`
	UA               string        `json:"ua"`
	EncrytType       string        `json:"encryt_type"`
	EncrytName       string        `json:"encryt_name"`
	KeyName          string        `json:"key_name"`
	KeyUse           string        `json:"key_use"`
	KeyValue         string        `json:"key_value"`
	CreTime          string        `json:"cre_time"`
	UpdTime          string        `json:"upd_time"`
	AutoUpdate       string        `json:"auto_update"`
	Status           string        `json:"status"`
	KeyDomain        string        `json:"key_domain,omitempty"`
	DemoNodeID       string        `json:"demo_node_id,omitempty"`
	DemoRecordID     string        `json:"demo_record_id,omitempty"`
	DemoResultStatus string        `json:"demo_result_status,omitempty"`
	PQMode           string        `json:"pq_mode,omitempty"`
}

// KeyEnrollPayload Kafka 消息协议结构
//
// 注意：这里**不再有 raw_password 字段**。
// 历史上它把用户的**明文口令**随密钥材料一起投递到 Kafka（PLAINTEXT），
// 而消费端 GenerateKafkaConsumer 早已明确忽略该字段（只打印一条"已忽略"的告警）。
// 也就是说：它没有任何用途，却让明文口令经过了一条本不必要的链路。
// 现已从协议中移除；消费端对旧消息里多出来的该字段是无害的（未知字段被忽略）。
type KeyEnrollPayload struct {
	RawUser      string    `json:"raw_user"`
	GeneratedKey Keymanage `json:"generated_key"`
	ActionType   string    `json:"action_type"`
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
