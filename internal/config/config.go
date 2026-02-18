package config

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/viper"
)

type Config struct {
	Server   ServerConfig   `mapstructure:"server"`
	Docker   DockerConfig   `mapstructure:"docker"`
	MCP      MCPConfig      `mapstructure:"mcp"`
	Web      WebConfig      `mapstructure:"web"`
	EnvFiles []string       `mapstructure:"envFiles"`
}

type ServerConfig struct {
	Host string `mapstructure:"host"`
	Port int    `mapstructure:"port"`
}

type DockerConfig struct {
	Network       string `mapstructure:"network"`
	ImagePrefix   string `mapstructure:"imagePrefix"`
	RestartPolicy string `mapstructure:"restartPolicy"`
	SocketPath    string `mapstructure:"socketPath"`
}

type MCPConfig struct {
	Enabled []MCPService `mapstructure:"enabled"`
}

type MCPService struct {
	Name        string            `mapstructure:"name"`
	DisplayName string            `mapstructure:"displayName"`
	Description string            `mapstructure:"description"`
	Image       string            `mapstructure:"image"`
	Command     string            `mapstructure:"command"`
	Args        []string          `mapstructure:"args"`
	Env         []EnvVar          `mapstructure:"env"`
	Port        int               `mapstructure:"port"`
	Enabled     bool              `mapstructure:"enabled"`
	Status      string            `mapstructure:"status"`
	Tools       []MCPTool         `mapstructure:"tools"`
	HealthCheck HealthCheckConfig `mapstructure:"healthCheck"`
}

type EnvVar struct {
	Name      string `mapstructure:"name"`
	Value     string `mapstructure:"value"`
	ValueFrom string `mapstructure:"valueFrom"` // env: or secret:
}

type HealthCheckConfig struct {
	Enabled  bool   `mapstructure:"enabled"`
	Interval string `mapstructure:"interval"`
	URL      string `mapstructure:"url"`
}

type MCPTool struct {
	Name        string                 `mapstructure:"name"`
	Description string                 `mapstructure:"description"`
	InputSchema map[string]interface{} `mapstructure:"inputSchema"`
	Example     map[string]interface{}  `mapstructure:"example"`
}

type WebConfig struct {
	Enable  bool   `mapstructure:"enable"`
	Port    int    `mapstructure:"port"`
	Title   string `mapstructure:"title"`
}

func Load(configPath string) (*Config, error) {
	viper.SetConfigFile(configPath)
	
	// 加载环境变量
	viper.SetEnvPrefix("CLAWMCP")
	viper.AutomaticEnv()
	
	// 支持环境变量中的下划线转驼峰
	replacer := strings.NewReplacer(".", "_")
	viper.SetEnvKeyReplacer(replacer)
	
	if err := viper.ReadInConfig(); err != nil {
		return nil, fmt.Errorf("failed to read config: %w", err)
	}
	
	var config Config
	if err := viper.Unmarshal(&config); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}
	
	// 设置默认值
	if config.Server.Port == 0 {
		config.Server.Port = 8080
	}
	if config.Web.Port == 0 {
		config.Web.Port = 8081
	}
	if config.Docker.Network == "" {
		config.Docker.Network = "clawmcp-network"
	}
	if config.Docker.SocketPath == "" {
		config.Docker.SocketPath = "/var/run/docker.sock"
	}
	
	// 加载 .env 文件
	if len(config.EnvFiles) > 0 {
		for _, envFile := range config.EnvFiles {
			if err := loadEnvFile(envFile); err != nil {
				fmt.Printf("Warning: failed to load env file %s: %v\n", envFile, err)
			}
		}
	}
	
	return &config, nil
}

func loadEnvFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		
		os.Setenv(key, value)
	}
	
	return nil
}
