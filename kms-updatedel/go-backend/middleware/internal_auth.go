package middleware

import (
	"key-service-lifecycle/config"

	"github.com/gofiber/fiber/v2"
)

const InternalTokenHeader = "X-Internal-Token"

// InternalAuth validates trusted internal service traffic.
func InternalAuth() fiber.Handler {
	return func(c *fiber.Ctx) error {
		token := c.Get(InternalTokenHeader)
		if token == "" {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"code": 401,
				"msg":  "缺少内部鉴权 Token，拒绝访问",
			})
		}
		if token != config.Get().InternalToken {
			return c.Status(fiber.StatusForbidden).JSON(fiber.Map{
				"code": 403,
				"msg":  "内部鉴权 Token 无效",
			})
		}
		return c.Next()
	}
}
