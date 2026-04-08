package main

import (
	"encoding/json"
	"log"
	"runtime"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"key-service-generate/config"
	"key-service-generate/controllers"
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

	api := app.Group("/generate/request")
	{
		api.Post("/Register", reqCtrl.Register)
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
