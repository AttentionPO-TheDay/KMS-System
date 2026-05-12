package controllers

import (
	"fmt"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"

	"key-service-lifecycle/models"
	"key-service-lifecycle/service"
)

// RequestController handles UPDATE_KEY and REVOKE_KEY endpoints.
type RequestController struct {
	lifecycleService *service.KeyLifecycleService
	idempService     *service.IdempotencyService
}

// NewRequestController creates a new RequestController.
func NewRequestController(lc *service.KeyLifecycleService, idem *service.IdempotencyService) *RequestController {
	return &RequestController{
		lifecycleService: lc,
		idempService:     idem,
	}
}

// updateKeyRequest matches the unified parameter name keyId.
type updateKeyRequest struct {
	KeyId      int64  `json:"keyId"`
	User       string `json:"user"`
	Password   string `json:"password"`
	UA         string `json:"ua"`
	EncrytType string `json:"encrytType"`
	EncrytName string `json:"encrytName"`
	KeyName    string `json:"keyName"`
	KeyUse     string `json:"keyUse"`
	AutoUpdate string `json:"autoUpdate"`
	KeyDomain  string `json:"keyDomain"`
}

// batchUpdateKeysRequest accepts a small key batch and builds a tree-shaped update batch.
type batchUpdateKeysRequest struct {
	KeyIds     []int64 `json:"keyIds"`
	User       string  `json:"user"`
	Password   string  `json:"password"`
	UA         string  `json:"ua"`
	EncrytType string  `json:"encrytType"`
	EncrytName string  `json:"encrytName"`
	KeyName    string  `json:"keyName"`
	KeyUse     string  `json:"keyUse"`
	AutoUpdate string  `json:"autoUpdate"`
	KeyDomain  string  `json:"keyDomain"`
	TreeFanout int     `json:"treeFanout"`
	ProofMode  string  `json:"proofMode"`
}

// revokeKeyRequest matches the unified parameter name keyId.
type revokeKeyRequest struct {
	KeyId    int64  `json:"keyId"`
	User     string `json:"user"`
	Password string `json:"password"`
}

// UpdateKey handles POST /lifecycle/request/UPDATE_KEY
func (c *RequestController) UpdateKey(ctx *fiber.Ctx) error {
	traceId := uuid.New().String()
	start := time.Now()

	var req updateKeyRequest
	if err := ctx.BodyParser(&req); err != nil {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"参数解析失败: "+err.Error(), traceId)
	}

	if req.KeyId == 0 || req.User == "" {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"必填参数缺失(keyId/user)", traceId)
	}

	idempotencyKey := ctx.Get("Idempotency-Key")
	if idempotencyKey == "" {
		idempotencyKey = fmt.Sprintf("UPDATE_KEY:%d:%s", req.KeyId, req.User)
	}
	ok, err := c.idempService.CheckAndSetWithKey(idempotencyKey)
	if err != nil {
		return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusError,
			"幂等校验不可用: "+err.Error(), traceId)
	}
	if !ok {
		service.IncrementDuplicate()
		return duplicateRequestResponse(ctx, traceId, "更新请求已接收，请勿重复提交")
	}

	keyInfo := &models.Keymanage{
		KeyID:      req.KeyId,
		UserName:   req.User,
		UA:         req.UA,
		EncrytType: req.EncrytType,
		EncrytName: req.EncrytName,
		KeyName:    req.KeyName,
		KeyUse:     req.KeyUse,
		AutoUpdate: req.AutoUpdate,
		KeyDomain:  req.KeyDomain,
	}

	payload := service.NewKeyLifecyclePayload(
		traceId,
		service.ActionUpdateKey,
		req.User,
		req.Password,
		req.KeyId,
		keyInfo,
	)
	applySingleProofContext(payload, traceId)

	if err := c.lifecycleService.EnqueueUpdate(payload); err != nil {
		return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusQueueFull,
			"更新请求投递失败: "+err.Error(), traceId)
	}

	elapsed := time.Since(start)
	fmt.Printf("[INFO][%s] UPDATE_KEY accepted keyId=%d user=%s elapsed=%v\n",
		traceId, req.KeyId, req.User, elapsed)

	return ctx.JSON(fiber.Map{
		"code":      200,
		"status":    models.StatusAccepted,
		"msg":       "更新请求已接收，正在后台处理",
		"trace_id":  traceId,
		"data":      "processing_async",
		"elapsedMs": elapsed.Milliseconds(),
	})
}

// BatchUpdateKeys handles POST /lifecycle/request/BATCH_UPDATE_KEYS
func (c *RequestController) BatchUpdateKeys(ctx *fiber.Ctx) error {
	traceId := uuid.New().String()
	start := time.Now()

	var req batchUpdateKeysRequest
	if err := ctx.BodyParser(&req); err != nil {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"参数解析失败: "+err.Error(), traceId)
	}

	keyIds := distinctKeyIDs(req.KeyIds)
	if len(keyIds) == 0 || req.User == "" {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"必填参数缺失(keyIds/user)", traceId)
	}

	batchID := uuid.New().String()
	fanout := normalizeTreeFanout(req.TreeFanout)
	proofMode := strings.TrimSpace(req.ProofMode)
	if proofMode == "" {
		proofMode = "semi_honest"
	}

	accepted := 0
	duplicates := 0
	for index, keyID := range keyIds {
		idempotencyKey := fmt.Sprintf("BATCH_UPDATE_KEYS:%d:%s", keyID, req.User)
		if headerKey := ctx.Get("Idempotency-Key"); headerKey != "" {
			idempotencyKey = fmt.Sprintf("%s:%d", headerKey, keyID)
		}

		ok, err := c.idempService.CheckAndSetWithKey(idempotencyKey)
		if err != nil {
			return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusError,
				"幂等校验不可用: "+err.Error(), traceId)
		}
		if !ok {
			service.IncrementDuplicate()
			duplicates++
			continue
		}

		keyInfo := &models.Keymanage{
			KeyID:      keyID,
			UserName:   req.User,
			UA:         req.UA,
			EncrytType: req.EncrytType,
			EncrytName: req.EncrytName,
			KeyName:    req.KeyName,
			KeyUse:     req.KeyUse,
			AutoUpdate: req.AutoUpdate,
			KeyDomain:  req.KeyDomain,
		}

		payload := service.NewKeyLifecyclePayload(
			traceId,
			service.ActionUpdateKey,
			req.User,
			req.Password,
			keyID,
			keyInfo,
		)
		parentBatchID, treePath, treeLevel := buildTreeMeta(batchID, len(keyIds), fanout, index)
		payload.BatchID = batchID
		payload.RootBatchID = batchID
		payload.ParentBatchID = parentBatchID
		payload.TreePath = treePath
		payload.TreeLevel = treeLevel
		payload.NodeIndex = index
		payload.ExpectedCount = len(keyIds)
		payload.TreeFanout = fanout
		payload.ProofMode = proofMode
		payload.CommitmentSeed = uuid.New().String()

		if err := c.lifecycleService.EnqueueUpdate(payload); err != nil {
			return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusQueueFull,
				"更新请求投递失败: "+err.Error(), traceId)
		}
		accepted++
	}

	elapsed := time.Since(start)
	fmt.Printf("[INFO][%s] BATCH_UPDATE_KEYS accepted batchId=%s total=%d accepted=%d duplicates=%d user=%s elapsed=%v\n",
		traceId, batchID, len(keyIds), accepted, duplicates, req.User, elapsed)

	return ctx.JSON(fiber.Map{
		"code":        200,
		"status":      models.StatusAccepted,
		"msg":         "批量更新请求已接收，正在按树型结构后台处理",
		"trace_id":    traceId,
		"batch_id":    batchID,
		"accepted":    accepted,
		"duplicates":  duplicates,
		"total":       len(keyIds),
		"tree_fanout": fanout,
		"proof_mode":  proofMode,
		"elapsedMs":   elapsed.Milliseconds(),
	})
}

// RevokeKey handles POST /lifecycle/request/REVOKE_KEY
func (c *RequestController) RevokeKey(ctx *fiber.Ctx) error {
	traceId := uuid.New().String()
	start := time.Now()

	var req revokeKeyRequest
	if err := ctx.BodyParser(&req); err != nil {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"参数解析失败: "+err.Error(), traceId)
	}

	if req.KeyId == 0 || req.User == "" {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"必填参数缺失(keyId/user)", traceId)
	}

	idempotencyKey := ctx.Get("Idempotency-Key")
	if idempotencyKey == "" {
		idempotencyKey = fmt.Sprintf("REVOKE_KEY:%d:%s", req.KeyId, req.User)
	}
	ok, err := c.idempService.CheckAndSetWithKey(idempotencyKey)
	if err != nil {
		return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusError,
			"幂等校验不可用: "+err.Error(), traceId)
	}
	if !ok {
		service.IncrementDuplicate()
		return duplicateRequestResponse(ctx, traceId, "回收请求已接收，请勿重复提交")
	}

	keyInfo := &models.Keymanage{
		KeyID:    req.KeyId,
		UserName: req.User,
	}

	payload := service.NewKeyLifecyclePayload(
		traceId,
		service.ActionRevokeKey,
		req.User,
		req.Password,
		req.KeyId,
		keyInfo,
	)

	if err := c.lifecycleService.EnqueueRevoke(payload); err != nil {
		return c.failResponse(ctx, fiber.StatusServiceUnavailable, models.StatusQueueFull,
			"回收请求投递失败: "+err.Error(), traceId)
	}

	elapsed := time.Since(start)
	fmt.Printf("[INFO][%s] REVOKE_KEY accepted keyId=%d user=%s elapsed=%v\n",
		traceId, req.KeyId, req.User, elapsed)

	return ctx.JSON(fiber.Map{
		"code":      200,
		"status":    models.StatusAccepted,
		"msg":       "回收请求已接收，正在后台处理",
		"trace_id":  traceId,
		"data":      nil,
		"elapsedMs": elapsed.Milliseconds(),
	})
}

// failResponse returns a structured error response.
func (c *RequestController) failResponse(ctx *fiber.Ctx, httpStatus int, status, message, traceId string) error {
	return ctx.Status(httpStatus).JSON(fiber.Map{
		"code":     httpStatus,
		"status":   status,
		"msg":      message,
		"trace_id": traceId,
	})
}

func duplicateRequestResponse(ctx *fiber.Ctx, traceId string, message string) error {
	return ctx.Status(fiber.StatusAccepted).JSON(fiber.Map{
		"code":     fiber.StatusAccepted,
		"status":   models.StatusDuplicate,
		"msg":      message,
		"trace_id": traceId,
	})
}

func applySingleProofContext(payload *models.KeyLifecyclePayload, traceId string) {
	payload.BatchID = traceId
	payload.RootBatchID = traceId
	payload.ParentBatchID = traceId
	payload.TreePath = traceId + "/0"
	payload.TreeLevel = 0
	payload.NodeIndex = 0
	payload.ExpectedCount = 1
	payload.TreeFanout = 1
	payload.ProofMode = "semi_honest"
	payload.CommitmentSeed = uuid.New().String()
}

func distinctKeyIDs(keyIDs []int64) []int64 {
	seen := make(map[int64]struct{}, len(keyIDs))
	result := make([]int64, 0, len(keyIDs))
	for _, keyID := range keyIDs {
		if keyID <= 0 {
			continue
		}
		if _, ok := seen[keyID]; ok {
			continue
		}
		seen[keyID] = struct{}{}
		result = append(result, keyID)
	}
	return result
}

func normalizeTreeFanout(value int) int {
	if value < 2 {
		return 8
	}
	if value > 128 {
		return 128
	}
	return value
}

func buildTreeMeta(batchID string, total, fanout, index int) (string, string, int) {
	if total <= 1 {
		return batchID, batchID + "/0", 0
	}
	group := index / fanout
	parentBatchID := fmt.Sprintf("%s/n%d", batchID, group)
	treeLevel := 1
	treePath := fmt.Sprintf("%s/%d/%d", batchID, group, index%fanout)
	return parentBatchID, treePath, treeLevel
}
