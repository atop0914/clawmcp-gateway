# ClawMCP Gateway 🦞

<p align="center">
  <img src="https://img.shields.io/badge/Go-1.21+-00ADD8?style=for-the-badge&logo=go" alt="Go">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

> MCP 服务管理平台 - 一键管理所有 MCP 服务

ClawMCP Gateway 是一个开源的 MCP（Model Context Protocol）服务管理平台，通过 Docker/uvx 统一运行和管理市面上的 MCP 服务，对外提供 HTTP API 和 Web 管理界面。

## ✨ 特性

- 🐳 **多种运行模式** - 支持 Docker 容器和 uvx/npx 直接运行
- 🌐 **HTTP API** - 统一的 RESTful API
- 🎨 **Web 管理界面** - 可视化服务管理（启动/停止/查看工具）
- 📝 **自动 Skill 生成** - OpenClaw 自动获取 MCP 服务能力
- ⚡ **高性能** - 基于 Go 的高性能服务
- 🔄 **热插拔** - 配置文件启用/禁用服务，无需重启

## 🚀 快速开始

### 前置要求

- Go 1.21+
- Docker (可选，用于容器模式)
- uvx 或 npx (用于直接运行模式)

### 1. 克隆项目

```bash
git clone https://github.com/atop0914/clawmcp-gateway.git
cd clawmcp-gateway
```

### 2. 配置

```bash
cp configs/.env.example configs/.env
# 编辑 .env 文件，填入你的 API Keys
```

**必须配置 MiniMax API Key:**
```
MINIMAX_API_KEY=你的MiniMax_API_Key
```
获取地址: https://platform.minimax.io/subscribe/coding-plan

### 3. 启动

```bash
# 方式一: 直接运行 (推荐)
go run ./cmd/server/main.go

# 方式二: Docker Compose
docker-compose up -d
```

### 4. 访问

- 🌐 Web 管理界面: http://localhost:8080
- 📡 API: http://localhost:8080/api/v1/services

## 📡 API 接口

### 获取所有服务

```bash
curl http://localhost:8080/api/v1/services
```

响应:
```json
{
  "success": true,
  "data": [
    {
      "name": "minimax-search",
      "displayName": "MiniMax 搜索",
      "description": "基于 MiniMax AI 的网络搜索服务",
      "status": "running",
      "port": 3001,
      "tools": [...]
    }
  ]
}
```

### 启动服务

```bash
curl -X POST http://localhost:8080/api/v1/services/minimax-search/start
```

### 停止服务

```bash
curl -X POST http://localhost:8080/api/v1/services/minimax-search/stop
```

### 调用工具

```bash
curl -X POST http://localhost:8080/api/v1/services/minimax-search/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"web_search","arguments":{"query":"golang教程"}}'
```

### 生成 Skill

```bash
curl http://localhost:8080/api/v1/services/minimax-search/skill
```

## 🎯 已支持的 MCP 服务

| 服务 | 功能 | 状态 |
|------|------|------|
| minimax-search | MiniMax 网络搜索 | ✅ 默认启用 |
| minimax-image | MiniMax 图像理解 | 🔄 |
| tavily-search | Tavily AI 搜索 | 🔄 |
| exa-search | Exa 神经搜索 | 🔄 |
| brave-search | Brave 搜索 | 🔄 |
| github | GitHub 集成 | 🔄 |
| puppeteer | 浏览器自动化 | 🔄 |
| filesystem | 文件系统访问 | 🔄 |
| postgres | PostgreSQL | 🔄 |
| sqlite | SQLite | 🔄 |
| memory | 记忆服务 | 🔄 |

## ⚙️ 配置说明

配置文件: `configs/config.yaml`

```yaml
mcp:
  enabled:
    - name: minimax-search      # 服务名称
      displayName: "MiniMax 搜索"  # 显示名称
      description: "描述"        # 服务描述
      command: "uvx"            # 运行命令
      args: ["minimax-coding-plan-mcp", "-y"]  # 参数
      env:                      # 环境变量
        - name: MINIMAX_API_KEY
          valueFrom: env:MINIMAX_API_KEY
      port: 3001                # HTTP 端口
      enabled: true             # 是否启用
```

## 🧩 OpenClaw 集成

在 OpenClaw 中配置定时任务自动同步:

```bash
# 获取服务列表
curl -s http://localhost:8080/api/v1/services

# 获取某个服务的 Skill
curl -s http://localhost:8080/api/v1/services/minimax-search/skill
```

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ClawMCP Gateway                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐            │
│  │  Config   │  │  Process  │  │   HTTP    │            │
│  │  Manager  │  │  Manager  │  │   Server   │            │
│  └───────────┘  └───────────┘  └───────────┘            │
└─────────────────────────────────────────────────────────────┘
          │               │
          ▼               ▼
    ┌─────────┐    ┌─────────┐
    │   uvx   │    │  Docker │
    │ process │    │ container│
    └─────────┘    └─────────┘
```

## 📝 License

MIT License

---

<p align="center">Made with ❤️ by ClawMCP Team</p>
