package main

/**
 * kms-updatedel Go Backend
 * 密钥更新与回收系统 - 高并发接入服务
 *
 * 端口：8082
 * API 前缀：/lifecycle/request/
 */

import (
	"fmt"
	"log"
	"runtime"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"key-service-lifecycle/config"
	"key-service-lifecycle/controllers"
	"key-service-lifecycle/middleware"
	"key-service-lifecycle/service"
	"key-service-lifecycle/utils"
)

func main() {
	// 1. Set max CPU cores
	runtime.GOMAXPROCS(runtime.NumCPU())

	// 2. Load configuration
	cfg := config.Get()
	fmt.Println("[INFO] Configuration loaded:")
	fmt.Printf("  ServerPort:    %s\n", cfg.ServerPort)
	fmt.Printf("  KafkaBrokers:  %s\n", cfg.KafkaBrokers)
	fmt.Printf("  UpdateTopic:   %s\n", cfg.UpdateTopic)
	fmt.Printf("  RevokeTopic:   %s\n", cfg.RevokeTopic)
	fmt.Printf("  RedisAddr:     %s\n", cfg.RedisAddr)

	// 3. Initialize Fiber app with Sonic for max performance
	app := fiber.New(fiber.Config{
		JSONEncoder:           utils.SonicMarshal,
		JSONDecoder:           utils.SonicUnmarshal,
		Prefork:               false,
		BodyLimit:             1 * 1024 * 1024, // 1MB
		DisableStartupMessage: false,
		ErrorHandler:          customErrorHandler,
	})

	// 4. Middleware
	app.Use(recover.New())
	app.Use(logger.New(logger.Config{
		Format: "[${time}] ${status} - ${latency} ${method} ${path}\n",
	}))

	// 5. Initialize services
	lcService := service.NewKeyLifecycleService()
	idempService := service.GetIdempotencyService()
	defer func() {
		lcService.Close()
		idempService.Close()
	}()

	// 6. Initialize controller
	reqCtrl := controllers.NewRequestController(lcService, idempService)

	// 7. Routes — prefix /lifecycle/request/
	api := app.Group("/lifecycle/request", middleware.InternalAuth())
	api.Post("/UPDATE_KEY", reqCtrl.UpdateKey)
	api.Post("/BATCH_UPDATE_KEYS", reqCtrl.BatchUpdateKeys)
	api.Post("/REVOKE_KEY", reqCtrl.RevokeKey)

	// 8. Monitoring endpoint — prefix /lifecycle/
	app.Get("/lifecycle/ping", pingHandler)
	app.Get("/lifecycle/metrics", metricsHandler)

	// 9. Start server
	addr := ":" + cfg.ServerPort
	log.Printf("kms-updatedel Fiber Server starting on %s", addr)
	if err := app.Listen(addr); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
}

func pingHandler(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"status":  "pong",
		"service": "kms-updatedel-go-backend",
	})
}

func metricsHandler(c *fiber.Ctx) error {
	m := service.GetMetrics()
	return c.JSON(fiber.Map{
		"update_requests":    m.UpdateRequests,
		"update_success":     m.UpdateSuccess,
		"update_queue_full":  m.UpdateQueueFull,
		"update_errors":      m.UpdateErrors,
		"revoke_requests":    m.RevokeRequests,
		"revoke_success":     m.RevokeSuccess,
		"revoke_queue_full":  m.RevokeQueueFull,
		"revoke_errors":      m.RevokeErrors,
		"duplicate_requests": m.DuplicateRequests,
	})
}

func customErrorHandler(c *fiber.Ctx, err error) error {
	code := fiber.StatusInternalServerError
	if e, ok := err.(*fiber.Error); ok {
		code = e.Code
	}
	return c.Status(code).JSON(fiber.Map{
		"code":   code,
		"status": "error",
		"msg":    err.Error(),
	})
}
