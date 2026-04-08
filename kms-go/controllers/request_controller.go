package controllers

import (
	"key-service/models"
	"key-service/service"

	"github.com/gofiber/fiber/v2"
)

type RequestController struct {
	keyService *service.KeyManageService
}

func NewRequestController(keyService *service.KeyManageService) *RequestController {
	return &RequestController{
		keyService: keyService,
	}
}

// EnrollKey 核心：密钥生成请求 (保持不变)
// 只有生成需要 Go 计算，所以参数最全
func (c *RequestController) EnrollKey(ctx *fiber.Ctx) error {
	// 1. 定义请求结构
	var req struct {
		User       string `json:"user"`
		Password   string `json:"password"`
		EncrytType string `json:"encryt_type"`
		EncrytName string `json:"encryt_name"`
		UA         string `json:"ua"`
		KeyDomain  string `json:"key_domain"`
	}

	// 2. 极速解析
	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	// 简单校验
	if req.User == "" || req.Password == "" || req.UA == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "必填参数缺失(User/Password/UA)",
		})
	}

	// 3. 构造 Model
	km := &models.Keymanage{
		UserName:   req.User,
		EncrytType: req.EncrytType,
		EncrytName: req.EncrytName,
		UA:         req.UA,
		KeyDomain:  req.KeyDomain,
		Status:     "0", // 0=Active
		KeyName:    "example",
		KeyUse:     "加解密",
		AutoUpdate: "false",
	}

	// 4. 调用 Service (Go 本地计算密钥 -> 发送 Kafka ENROLL)
	keyValue, err := c.keyService.EnrollKey(km, req.Password)
	if err != nil {
		return ctx.Status(fiber.StatusServiceUnavailable).JSON(fiber.Map{
			"code": 500, "msg": "密钥生成失败: " + err.Error(),
		})
	}

	// 5. 返回结果
	return ctx.Status(fiber.StatusOK).JSON(fiber.Map{
		"code": 200,
		"msg":  "操作成功",
		"data": keyValue,
	})
}

// UpdateKey 密钥轮换/更新 (轻量级转发)
// 前端只需传 KeyId，Go 不负责生成，直接转发给 Java 处理
func (c *RequestController) UpdateKey(ctx *fiber.Ctx) error {
	// 1. 定义简化的请求结构
	var req struct {
		KeyId    int64  `json:"key_id"`   // 必填：用于定位
		User     string `json:"user"`     // 必填：用于鉴权
		Password string `json:"password"` // 必填：用于鉴权
	}

	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	// 2. 校验
	if req.KeyId == 0 || req.User == "" || req.Password == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "必填参数缺失(KeyId/User/Password)",
		})
	}

	// 3. 构造 Model (只传 ID 和 User 给 Service)
	km := &models.Keymanage{
		KeyID:    req.KeyId,
		UserName: req.User,
	}

	// 4. 调用 Service (直接发送 Kafka UPDATE 消息)
	// Go Service 内部不再查库，也不生成密钥，直接转发
	msg, err := c.keyService.UpdateKey(km, req.Password)
	if err != nil {
		return ctx.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"code": 500, "msg": "更新请求发送失败: " + err.Error(),
		})
	}

	// 5. 返回异步处理结果
	return ctx.JSON(fiber.Map{
		"code": 200,
		"msg":  "更新请求已接收，正在后台处理",
		"data": msg, // 返回 "processing_async"
	})
}

// RevokeKey 密钥回收/删除 (轻量级转发)
func (c *RequestController) RevokeKey(ctx *fiber.Ctx) error {
	var req struct {
		KeyID    int64  `json:"key_id"`
		User     string `json:"user"`
		Password string `json:"password"`
	}

	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	if req.KeyID == 0 || req.User == "" || req.Password == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "必填参数缺失(KeyId/User/Password)",
		})
	}

	// 调用 Service (直接发送 Kafka REVOKE 消息)
	err := c.keyService.RevokeKey(req.KeyID, req.User, req.Password)
	if err != nil {
		return ctx.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"code": 500, "msg": "回收请求发送失败: " + err.Error(),
		})
	}

	return ctx.JSON(fiber.Map{
		"code": 200,
		"msg":  "回收请求已接收，正在后台处理",
		"data": nil,
	})
}

// ReenrollKey 重新生成 (通常逻辑同 Enroll，或者复用 Update)
func (c *RequestController) ReenrollKey(ctx *fiber.Ctx) error {
	// 如果业务逻辑和 EnrollKey 一样，直接复用
	return c.EnrollKey(ctx)
}
