package main

import (
	"encoding/json"
	"log"
	"runtime"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"key-service-generate/config"
	"key-service-generate/controllers"
	"key-service-generate/middleware"
	"key-service-generate/service"
)

func main() {
	runtime.GOMAXPROCS(runtime.NumCPU())

	app := fiber.New(fiber.Config{
		JSONEncoder: json.Marshal,
		JSONDecoder: json.Unmarshal,
		Prefork:     false,
		BodyLimit:   1 * 1024 * 1024,
	})

	app.Use(recover.New())

	keyService := service.NewKeyManageService()
	defer keyService.Close()

	reqCtrl := controllers.NewRequestController(keyService)

	// Register 接口不需要内部鉴权（用于用户注册流程）
	app.Post("/generate/request/Register", reqCtrl.Register)

	// 以下接口仅允许 Java 后端（已完成用户鉴权）转发调用
	// 通过 X-Internal-Token Header 进行内部服务鉴权
	api := app.Group("/generate/request", middleware.InternalAuth())
	{
		api.Post("/ENROLL_KEY", reqCtrl.EnrollKey)
		api.Post("/REENROLL_KEY", reqCtrl.ReenrollKey)
		api.Post("/comparam", reqCtrl.ComParam)
	}

	app.Get("/generate/ping", func(c *fiber.Ctx) error {
		return c.SendString("pong")
	})

	log.Printf("Fiber Server starting on :%s", config.ServerPort)
	if err := app.Listen(":" + config.ServerPort); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
}

