package middleware

import (
	"strings"

	"github.com/gofiber/fiber/v2"
)

// VerifiedUserHeader 由 Java 业务层写入，携带已经过 Session/@PreAuthorize 校验的用户名。
//
// 信任模型：
//  1. 只有通过 InternalAuth（X-Internal-Token）的调用才会进入本中间件；
//  2. Java 控制器在转发前用当前登录态（SecurityUtils.getUsername()）覆盖该头；
//  3. Go 侧因此不再信任请求体中的 user 字段，杜绝伪造任意身份的生成请求。
const VerifiedUserHeader = "X-Kms-User"

// VerifiedUser 提取并规范化 Java 侧传入的已认证用户名。
//
// 返回值 ok=false 时调用方必须拒绝请求（而不是回退到请求体），
// 否则「头部缺失」就退化成「可伪造请求体」的旁路。
func VerifiedUser(c *fiber.Ctx) (string, bool) {
	user := strings.TrimSpace(c.Get(VerifiedUserHeader))
	if user == "" {
		return "", false
	}
	// 用户名不应包含控制字符或换行，防止头部注入
	if strings.ContainsAny(user, "\r\n\x00") {
		return "", false
	}
	return user, true
}
