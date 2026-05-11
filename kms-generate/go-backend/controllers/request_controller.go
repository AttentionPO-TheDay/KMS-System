package controllers

import (
	"key-service-generate/models"
	"key-service-generate/service"
	"regexp"
	"strings"

	"github.com/gofiber/fiber/v2"
)

var certlessUARegex = regexp.MustCompile(`^[0-9a-fA-F]+$`)

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
		DemoNodeID string `json:"demo_node_id"`
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

	req.EncrytType = strings.TrimSpace(req.EncrytType)
	req.EncrytName = strings.TrimSpace(req.EncrytName)
	req.UA = strings.TrimSpace(req.UA)
	req.DemoNodeID = strings.TrimSpace(req.DemoNodeID)

	if req.EncrytType == "无证书非对称加密" && (req.EncrytName == "SM2" || req.EncrytName == "SSCL") {
		if req.UA == "" {
			return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"code": 500, "msg": "无证书非对称加密必须提供用户部分公钥(UA)",
			})
		}
		if len(req.UA) != 130 {
			return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"code": 500, "msg": "用户部分公钥(UA)长度非法",
			})
		}
		if !strings.HasPrefix(strings.ToLower(req.UA), "04") {
			return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"code": 500, "msg": "用户部分公钥(UA)前缀非法",
			})
		}
		if !certlessUARegex.MatchString(req.UA) {
			return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"code": 500, "msg": "用户部分公钥(UA)必须为十六进制字符串",
			})
		}
	} else if service.IsPQAlgorithm(req.EncrytName) {
		if req.DemoNodeID == "" {
			return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"code": 500, "msg": "抗量子密钥生成必须提供 demo_node_id",
			})
		}
	} else {
		return ctx.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"code": 500, "msg": "加密算法仅支持 SM2、SSCL 或抗量子算法",
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
		autoUpdate = "0"
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
		DemoNodeID: req.DemoNodeID,
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
