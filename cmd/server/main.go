package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/gin-gonic/gin"

	"clawmcp-gateway/internal/config"
	"clawmcp-gateway/internal/docker"
	"clawmcp-gateway/internal/handler"
)

func main() {
	// 加载配置
	configPath := os.Getenv("CLAWMCP_CONFIG")
	if configPath == "" {
		configPath = "./config.yaml"
	}

	cfg, err := config.Load(configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// 创建 Docker 管理器
	dockerMgr, err := docker.NewManager(cfg)
	if err != nil {
		log.Fatalf("Failed to create docker manager: %v", err)
	}
	defer dockerMgr.Close()

	// 创建处理器
	h := handler.NewHandler(dockerMgr, cfg)

	// 设置 Gin
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	// CORS
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	})

	// 健康检查
	r.GET("/health", h.HealthCheck)

	// Web UI
	if cfg.Web.Enable {
		r.GET("/", h.WebUI)
	}

	// API v1
	v1 := r.Group("/api/v1")
	{
		// 服务管理
		v1.GET("/services", h.GetServices)
		v1.GET("/services/:name", h.GetService)
		v1.POST("/services/:name/start", h.StartService)
		v1.POST("/services/:name/stop", h.StopService)
		v1.DELETE("/services/:name", h.RemoveService)

		// 工具调用
		v1.POST("/services/:name/call", h.CallTool)

		// 日志
		v1.GET("/services/:name/logs", h.GetServiceLogs)

		// Skill 生成
		v1.GET("/services/:name/skill", h.GenerateSkill)
	}

	// 启动服务器
	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port)
	log.Printf("Starting ClawMCP Gateway on %s", addr)
	log.Printf("Web UI: http://%s/", addr)

	// 优雅关闭
	go func() {
		if err := r.Run(addr); err != nil {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// 等待信号
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down...")
	log.Println("Server stopped")
}
