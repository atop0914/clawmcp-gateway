# ClawMCP Gateway 🦞

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

> MCP 服务管理平台 - 一键管理所有 MCP 服务

ClawMCP Gateway 是一个开源的 MCP（Model Context Protocol）服务管理平台，通过 HTTP 统一运行和管理市面上的 MCP 服务，对外提供 HTTP API 和 Web 管理界面。

## ✨ 特性

- 🐍 **纯 Python** - 与 MCP 生态完美融合
- 🌐 **HTTP API** - 统一的 RESTful API
- 🎨 **Web 管理界面** - 可视化服务管理（启动/停止/查看工具）
- ⚡ **高性能** - 基于 FastAPI + Uvicorn
- 🔄 **热插拔** - 配置文件启用/禁用服务，无需重启

## 🚀 快速开始

### 前置要求

- Python 3.12+
- pip

### 1. 安装依赖

```bash
pip install httpx fastapi uvicorn pyyaml
```

### 2. 克隆项目

```bash
git clone https://github.com/atop0914/clawmcp-gateway.git
cd clawmcp-gateway
```

### 3. 配置

```bash
cp configs/.env.example configs/.env
# 编辑 .env 文件，填入你的 API Keys
```

**必须配置 MiniMax API Key:**
```
MINIMAX_API_KEY=你的MiniMax_API_Key
```
获取地址: https://platform.minimax.io/subscribe/coding-plan

### 4. 启动

```bash
# 方式一: 直接运行
python3 gateway.py

# 方式二: 指定端口
CLAWMCP_PORT=8080 python3 gateway.py
```

### 5. 访问

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
      "port": 3001
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

## 🎯 已支持的 MCP 服务

| 服务 | 功能 | 状态 |
|------|------|------|
| minimax-search | MiniMax 网络搜索 | ✅ |
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
    - name: minimax-search
      displayName: "MiniMax 搜索"
      description: "基于 MiniMax AI 的网络搜索服务"
      command: "uvx"
      args: ["minimax-coding-plan-mcp", "-y"]
      env:
        - name: MINIMAX_API_KEY
          valueFrom: env:MINIMAX_API_KEY
        - name: MINIMAX_API_HOST
          value: "https://api.minimaxi.com"
      port: 3001
      enabled: true
```

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ClawMCP Gateway                        │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐            │
│  │  Config   │  │  FastAPI │  │  Web UI  │            │
│  │  Manager  │  │   Server  │  │           │            │
│  └───────────┘  └───────────┘  └───────────┘            │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
    ┌─────────┐
    │  MCP   │
    │ Servers │
    └─────────┘
```

## 📝 License

MIT License

---

<p align="center">Made with ❤️ by ClawMCP Team</p>
