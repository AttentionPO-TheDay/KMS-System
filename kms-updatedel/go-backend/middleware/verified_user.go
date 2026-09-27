package middleware

import (
	"strings"

	"github.com/gofiber/fiber/v2"
)

// VerifiedUserHeader 由 Java 业务层写入，携带已经过会话鉴权（并已校验密钥归属）的用户名。
//
// 信任模型：
//  1. 只有通过 InternalAuth（X-Internal-Token）的调用才会进入本中间件；
//  2. Java 控制器在转发前写入目标密钥的所有者；
//  3. Go 侧因此不再信任请求体中的 user 字段，
//     杜绝伪造任意身份触达「更新 / 回收 / 批量回收」。
const VerifiedUserHeader = "X-Kms-User"

// VerifiedUser 提取并规范化 Java 侧传入的已认证用户名。
//
// 返回 ok=false 时调用方必须拒绝请求，不得回退到请求体，
// 否则「头部缺失」会退化成「可伪造请求体」的旁路。
func VerifiedUser(c *fiber.Ctx) (string, bool) {
	user := strings.TrimSpace(c.Get(VerifiedUserHeader))
	if user == "" {
		return "", false
	}
	if strings.ContainsAny(user, "\r\n\x00") {
		return "", false
	}
	return user, true
}
