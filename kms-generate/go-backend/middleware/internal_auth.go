package middleware

import (
	"key-service-generate/config"

	"github.com/gofiber/fiber/v2"
)

const InternalTokenHeader = "X-Internal-Token"

// InternalAuth 中间件：验证请求是否来自受信任的内部服务（Java 后端）
// Java 端已完成用户鉴权，只需携带约定的内部 Token 即可放行，无需用户密码
func InternalAuth() fiber.Handler {
	return func(c *fiber.Ctx) error {
		token := c.Get(InternalTokenHeader)
		if token == "" {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"code": 401,
				"msg":  "缺少内部鉴权 Token，拒绝访问",
			})
		}
		if token != config.InternalToken {
			return c.Status(fiber.StatusForbidden).JSON(fiber.Map{
				"code": 403,
				"msg":  "内部鉴权 Token 无效",
			})
		}
		return c.Next()
	}
}
