package controllers

import (
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"

	"key-service-lifecycle/models"
	"key-service-lifecycle/service"
)

// RequestController handles UPDATE_KEY and REVOKE_KEY endpoints.
type RequestController struct {
	lifecycleService *service.KeyLifecycleService
	idempService    *service.IdempotencyService
}

// NewRequestController creates a new RequestController.
func NewRequestController(lc *service.KeyLifecycleService, idem *service.IdempotencyService) *RequestController {
	return &RequestController{
		lifecycleService: lc,
		idempService:    idem,
	}
}

// updateKeyRequest matches the unified parameter name keyId.
type updateKeyRequest struct {
	KeyId    int64  `json:"keyId"`
	User     string `json:"user"`
	Password string `json:"password"`
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

	// Parameter validation
	if req.KeyId == 0 || req.User == "" || req.Password == "" {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"必填参数缺失(keyId/user/password)", traceId)
	}

	// Idempotency check via Redis
	ok, err := c.idempService.CheckAndSet("UPDATE_KEY", req.KeyId, req.User)
	if err != nil {
		// Redis error — log but allow request to proceed
		fmt.Printf("[WARN][%s] Idempotency check error: %v\n", traceId, err)
	} else if !ok {
		// Duplicate detected
		service.GetMetrics() // update duplicate counter
		return c.failResponse(ctx, fiber.StatusAccepted, models.StatusDuplicate,
			"更新请求已接收，请勿重复提交", traceId)
	}

	// Build payload and enqueue
	payload := service.NewKeyLifecyclePayload(
		traceId,
		service.ActionUpdateKey,
		req.User,
		req.Password,
		req.KeyId,
		nil,
	)

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

// RevokeKey handles POST /lifecycle/request/REVOKE_KEY
func (c *RequestController) RevokeKey(ctx *fiber.Ctx) error {
	traceId := uuid.New().String()
	start := time.Now()

	var req revokeKeyRequest
	if err := ctx.BodyParser(&req); err != nil {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"参数解析失败: "+err.Error(), traceId)
	}

	// Parameter validation
	if req.KeyId == 0 || req.User == "" || req.Password == "" {
		return c.failResponse(ctx, fiber.StatusBadRequest, models.StatusInvalidParam,
			"必填参数缺失(keyId/user/password)", traceId)
	}

	// Idempotency check via Redis
	ok, err := c.idempService.CheckAndSet("REVOKE_KEY", req.KeyId, req.User)
	if err != nil {
		fmt.Printf("[WARN][%s] Idempotency check error: %v\n", traceId, err)
	} else if !ok {
		return c.failResponse(ctx, fiber.StatusAccepted, models.StatusDuplicate,
			"回收请求已接收，请勿重复提交", traceId)
	}

	// Build payload and enqueue
	payload := service.NewKeyLifecyclePayload(
		traceId,
		service.ActionRevokeKey,
		req.User,
		req.Password,
		req.KeyId,
		nil,
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
