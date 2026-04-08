package main

/**
 * kms-generate Go Backend
 * 密钥生成系统 - 高并发接入服务
 *
 * 职责：
 * 1. 高并发接收生成请求 (ENROLL_KEY, REENROLL_KEY)
 * 2. 执行 SM2/SSCL/AES 本地密钥生成计算
 * 3. 参数校验
 * 4. 异步写 Kafka (topic: key_generate_log)
 * 5. 提供高吞吐监控指标
 *
 * 目标性能：100000 TPS
 *
 * 端口：8081
 * API 前缀：/generate/request/
 */

import (
	"log"
	"runtime"

	"github.com/bytedance/sonic"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"

	// TODO: Agent 2 将填充以下模块
	// "key-service-generate/controllers"
	// "key-service-generate/service"
)

func main() {
	// 1. 设置最大核心数
	runtime.GOMAXPROCS(runtime.NumCPU())

	// 2. 初始化 Fiber 应用
	app := fiber.New(fiber.Config{
		// 极致性能配置
		JSONEncoder: sonic.Marshal,
		JSONDecoder: sonic.Unmarshal,
		Prefork:     false,
		BodyLimit:   1 * 1024 * 1024, // 1MB
		DisableStartupMessage: false,
	})

	// 3. 中间件
	app.Use(recover.New())

	// TODO: Agent 2 - 以下代码将由 Agent 2 填充
	// 4. 初始化 Service
	// keyService := service.NewKeyManageService()
	// defer keyService.Close()
	//
	// 5. 初始化 Controller
	// reqCtrl := controllers.NewRequestController(keyService)
	//
	// 6. 路由配置
	// api := app.Group("/generate/request")
	// {
	// 	api.Post("/Register", reqCtrl.Register)
	// 	api.Post("/ENROLL_KEY", reqCtrl.EnrollKey)
	// 	api.Post("/REENROLL_KEY", reqCtrl.ReenrollKey)
	// 	api.Post("/comparam", reqCtrl.GetComParam)
	// }

	// 健康检查
	app.Get("/generate/ping", func(c *fiber.Ctx) error {
		return c.SendString("pong")
	})

	// 7. 启动服务
	log.Println("kms-generate Fiber Server starting on :8081")
	if err := app.Listen(":8081"); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
}
