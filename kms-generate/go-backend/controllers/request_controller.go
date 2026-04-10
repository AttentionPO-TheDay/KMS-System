package controllers

import (
	"key-service-generate/models"
	"key-service-generate/service"

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

func (c *RequestController) Register(ctx *fiber.Ctx) error {
	var req struct {
		User     string `json:"user"`
		Password string `json:"password"`
	}

	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	if req.User == "" || req.Password == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "必填参数缺失(User/Password)",
		})
	}

	if err := c.keyService.Register(req.User, req.Password); err != nil {
		return ctx.Status(fiber.StatusServiceUnavailable).JSON(fiber.Map{
			"code": 500, "msg": "注册失败: " + err.Error(),
		})
	}

	return ctx.Status(fiber.StatusOK).JSON(fiber.Map{
		"code": 200,
		"msg":  "操作成功",
	})
}

func (c *RequestController) EnrollKey(ctx *fiber.Ctx) error {
	var req struct {
		User       string `json:"user"`
		EncrytType string `json:"encryt_type"`
		EncrytName string `json:"encryt_name"`
		UA         string `json:"ua"`
		KeyDomain  string `json:"key_domain"`
		KeyName    string `json:"key_name"`
		KeyUse     string `json:"key_use"`
		AutoUpdate string `json:"auto_update"`
	}

	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	if req.User == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "必填参数缺失(User)",
		})
	}

	// 无证书非对称加密必须提供用户部分公钥 uA
	if (req.EncrytType == "无证书非对称加密") && req.UA == "" {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "无证书非对称加密必须提供用户部分公钥(UA)",
		})
	}

	keyName := req.KeyName
	if keyName == "" {
		keyName = "example"
	}
	keyUse := req.KeyUse
	if keyUse == "" {
		keyUse = "加解密"
	}
	autoUpdate := req.AutoUpdate
	if autoUpdate == "" {
		autoUpdate = "false"
	}

	km := &models.Keymanage{
		UserName:   req.User,
		EncrytType: req.EncrytType,
		EncrytName: req.EncrytName,
		UA:         req.UA,
		KeyDomain:  req.KeyDomain,
		Status:     "0",
		KeyName:    keyName,
		KeyUse:     keyUse,
		AutoUpdate: autoUpdate,
	}

	// 由内部 Token 保证身份，不再需要明文密码鉴权
	// 传空字符串作为 rawPassword，Kafka 消息中 Java 端将基于 Session 用户信息补充
	keyValue, err := c.keyService.EnrollKey(km, "")
	if err != nil {
		return ctx.Status(fiber.StatusServiceUnavailable).JSON(fiber.Map{
			"code": 500, "msg": "密钥生成失败: " + err.Error(),
		})
	}

	return ctx.Status(fiber.StatusOK).JSON(fiber.Map{
		"code": 200,
		"msg":  "操作成功",
		"data": keyValue,
	})
}

func (c *RequestController) ReenrollKey(ctx *fiber.Ctx) error {
	return c.EnrollKey(ctx)
}

func (c *RequestController) ComParam(ctx *fiber.Ctx) error {
	var req struct {
		EncrytType string `json:"encryt_type"`
		EncrytName string `json:"encryt_name"`
	}

	if err := ctx.BodyParser(&req); err != nil {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "参数解析失败: " + err.Error(),
		})
	}

	data := c.keyService.GetComParam(req.EncrytType, req.EncrytName)
	if data == nil {
		return ctx.Status(fiber.StatusOK).JSON(fiber.Map{
			"code": 200,
			"msg":  "操作成功",
			"data": fiber.Map{},
		})
	}

	return ctx.Status(fiber.StatusOK).JSON(fiber.Map{
		"code": 200,
		"msg":  "操作成功",
		"data": data,
	})
}
