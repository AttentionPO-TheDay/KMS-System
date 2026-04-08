package main

import (
	"log"
	"runtime"

	"github.com/bytedance/sonic"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"key-service/controllers"
	"key-service/service"
)

func main() {
	// 1. 设置最大核心数
	runtime.GOMAXPROCS(runtime.NumCPU())

	// 2. 初始化 Fiber 应用
	app := fiber.New(fiber.Config{
		// --- 极致性能配置 ---

		// 替换 JSON 编码/解码器为 Sonic
		JSONEncoder: sonic.Marshal,
		JSONDecoder: sonic.Unmarshal,

		// 预分叉模式 (Prefork): 如果开启，Fiber 会启动多个进程监听端口。
		// 配合 Linux SO_REUSEPORT，可以极大提升吞吐量。
		// 开发环境建议 false，生产环境压测时可以改为 true 试试
		Prefork: false,

		// 减少内存分配：BodyLimit 限制请求大小 (例如 1MB)
		BodyLimit: 1 * 1024 * 1024,

		// 禁用 Startup Message (可选，只是为了控制台干净)
		DisableStartupMessage: false,
	})

	// 3. 中间件
	app.Use(recover.New())
	// 高并发压测时，建议关闭 Logger 中间件，因为控制台 I/O 会成为瓶颈
	// app.Use(logger.New())

	// 4. 初始化 Service
	keyService := service.NewKeyManageService()
	defer keyService.Close()

	// 5. 初始化 Controller
	reqCtrl := controllers.NewRequestController(keyService)

	// 6. 路由配置
	// Java Path: /keymanage/request
	api := app.Group("/keymanage/request")
	{
		api.Post("/ENROLL_KEY", reqCtrl.EnrollKey)
		api.Post("/REENROLL_KEY", reqCtrl.ReenrollKey)
		api.Post("/UPDATE_KEY", reqCtrl.UpdateKey)
		api.Post("/REVOKE_KEY", reqCtrl.RevokeKey)
	}

	// 健康检查
	app.Get("/ping", func(c *fiber.Ctx) error {
		return c.SendString("pong")
	})

	// 7. 启动服务
	log.Println("Fiber Server starting on :8081")
	if err := app.Listen(":8081"); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
}
