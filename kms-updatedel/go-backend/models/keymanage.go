package models

// Keymanage is the core domain model for key lifecycle management.
type Keymanage struct {
	KeyID      int64  `json:"key_id,omitempty"`
	UserID     int64  `json:"user_id,omitempty"`
	UserName   string `json:"user_name"`
	UA         string `json:"ua,omitempty"`
	EncrytType string `json:"encryt_type,omitempty"`
	EncrytName string `json:"encryt_name,omitempty"`
	KeyName    string `json:"key_name,omitempty"`
	KeyUse     string `json:"key_use,omitempty"`
	KeyValue   string `json:"key_value,omitempty"`
	CreTime    string `json:"cre_time,omitempty"`
	UpdTime    string `json:"upd_time,omitempty"`
	AutoUpdate string `json:"auto_update,omitempty"`
	Status     string `json:"status,omitempty"`
	KeyDomain  string `json:"key_domain,omitempty"`
}

// KeyLifecyclePayload is the Kafka message structure for UPDATE_KEY and REVOKE_KEY.
type KeyLifecyclePayload struct {
	TraceID        string    `json:"trace_id"`
	ActionType     string    `json:"action_type"` // UPDATE_KEY or REVOKE_KEY
	RawUser        string    `json:"raw_user"`
	RawPassword    string    `json:"raw_password"`
	KeyID          int64     `json:"key_id"`
	KeyInfo        Keymanage `json:"key_info"`
	BatchID        string    `json:"batch_id,omitempty"`
	ParentBatchID  string    `json:"parent_batch_id,omitempty"`
	RootBatchID    string    `json:"root_batch_id,omitempty"`
	TreePath       string    `json:"tree_path,omitempty"`
	TreeLevel      int       `json:"tree_level,omitempty"`
	NodeIndex      int       `json:"node_index,omitempty"`
	ExpectedCount  int       `json:"expected_count,omitempty"`
	TreeFanout     int       `json:"tree_fanout,omitempty"`
	ProofMode      string    `json:"proof_mode,omitempty"`
	CommitmentSeed string    `json:"commitment_seed,omitempty"`
}

// Standard response status codes for lifecycle operations.
const (
	StatusAccepted     = "accepted"
	StatusDuplicate    = "duplicate"
	StatusQueueFull    = "queue_full"
	StatusAuthFailed   = "auth_failed"
	StatusInvalidParam = "invalid_param"
	StatusError        = "error"
)
