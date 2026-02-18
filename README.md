# ClawMCP Gateway

<p align="center">
  <img src="https://img.shields.io/badge/Go-1.21+-00ADD8?style=for-the-badge&logo=go" alt="Go">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

> 🦞 MCP 服务管理平台 - All-in-One MCP Hub

ClawMCP Gateway 是一个开源的 MCP（Model Context Protocol）服务管理平台，通过 Docker 容器化技术统一管理市面上的 MCP 服务，对外提供 HTTP API 和 Web 管理界面。

## ✨ 特性

- 🐳 **Docker 容器化** - 一键部署，无需手动配置
- 🌐 **HTTP API** - 统一的 RESTful API
- 🎨 **Web 管理界面** - 可视化服务管理
- 🔄 **动态服务发现** - 自动获取 MCP 服务能力
- 📝 **自动 Skill 生成** - OpenClaw 自动生成 SKILL.md
- ⚡ **高并发** - 基于 Go 的高性能服务

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/clawmcp-gateway.git
cd clawmcp-gateway
```

### 2. 配置

```bash
cp configs/.env.example configs/.env
# 编辑 .env 文件，填入你的 API Keys
```

### 3. 启动

```bash
# Docker Compose (推荐)
docker-compose up -d

# 或直接运行
go run cmd/server/main.go
```

### 4. 访问

- Web 管理界面: http://localhost:8080
- API 文档: http://localhost:8080/api/v1/services

## 📡 API 接口

### 获取所有服务

```bash
GET /api/v1/services
```

响应:
```json
{
  "success": true,
  "data": [
    {
      "name": "minimax-search",
      "displayName": "MiniMax 搜索",
      "description": "基于 MiniMax 的网络搜索服务",
      "status": "running",
      "port": 3001,
      "tools": [...]
    }
  ]
}
```

### 启动服务

```bash
POST /api/v1/services/{name}/start
```

### 停止服务

```bash
POST /api/v1/services/{name}/stop
```

### 调用工具

```bash
POST /api/v1/services/{name}/call
Content-Type: application/json

{
  "tool": "web_search",
  "arguments": {
    "query": "golang 教程"
  }
}
```

### 生成 Skill

```bash
GET /api/v1/services/{name}/skill
```

## 🎯 OpenClaw 集成

在 OpenClaw 中配置定时任务，自动获取 MCP 服务列表：

```yaml
# .openclaw/config.yaml
cron:
  mcp-sync:
    schedule: "0 * * * *"
    command: "curl -s http://localhost:8080/api/v1/services"
```

## ⚙️ 配置说明

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|-------|
| server.host | string | 服务监听地址 | 0.0.0.0 |
| server.port | int | 服务监听端口 | 8080 |
| web.enable | bool | 启用 Web 界面 | true |
| docker.network | string | Docker 网络名 | clawmcp-network |
| mcp.enabled | array | 启用的 MCP 服务 | [] |

### MCP 服务配置

```yaml
mcp:
  enabled:
    - name: service-name       # 服务名称
      displayName: "显示名称"  # 显示名称
      description: "描述"     # 服务描述
      image: "docker镜像"    # Docker 镜像
      port: 3001              # 映射端口
      enabled: true           # 是否启用
      env:                    # 环境变量
        - name: API_KEY
          valueFrom: env:ENV_VAR_NAME
```

## 🛠️ 已支持的 MCP 服务

| 服务 | 功能 | 状态 |
|------|------|------|
| minimax-search | MiniMax 搜索 | ✅ |
| tavily-search | Tavily AI 搜索 | 🔄 |
| filesystem | 文件系统访问 | 🔄 |
| brave-search | Brave 搜索 | 🔄 |
| github | GitHub 集成 | 🔄 |
| exa-search | Exa 神经搜索 | 🔄 |
| slack | Slack 集成 | 🔄 |
| notion | Notion 集成 | 🔄 |

## 🧩 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ClawMCP Gateway                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐            │
│  │  Config   │  │  Docker   │  │   HTTP    │            │
│  │  Manager  │  │  Manager  │  │   Server   │            │
│  └───────────┘  └───────────┘  └───────────┘            │
└─────────────────────────────────────────────────────────────┘
                    │           │           │
          ┌─────────┼───────────┼───────────┼─────────┐
          ▼         ▼           ▼           ▼         ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ minimax │ │  tavily │ │   git   │ │  other  │
    │   MCP   │ │   MCP   │ │   MCP   │ │   MCP   │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

<p align="center">Made with ❤️ by ClawMCP Team</p>
