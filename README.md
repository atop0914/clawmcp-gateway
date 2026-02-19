# ClawMCP Gateway 🦞

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

> MCP 服务管理平台 - 一键管理所有 MCP 服务

ClawMCP Gateway 是一个开源的 MCP（Model Context Protocol）服务管理平台，通过统一的 HTTP API 管理市面上的 MCP 服务。

## ✨ 特性

- 🐍 **纯 Python** - 与 MCP 生态完美融合
- 🌐 **HTTP API** - 统一的 RESTful API
- 🎨 **Web 管理界面** - 可视化服务管理
- ⚡ **高性能** - 基于 FastAPI + Uvicorn

## 快速开始

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
# 编辑 .env，填入你的 API Keys
```

### 4. 启动

```bash
# 方式一: 直接运行
python3 gateway.py

# 方式二: 指定端口
CLAWMCP_PORT=8080 python3 gateway.py
```

### 5. 访问

- 🌐 Web: http://localhost:8080
- 📡 API: http://localhost:8080/api/v1/services

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /api/v1/services | 获取服务列表 |
| POST | /api/v1/services/{name}/start | 启动服务 |
| POST | /api/v1/services/{name}/stop | 停止服务 |
| POST | /api/v1/services/{name}/call | 调用工具 |

## 示例

```bash
# 获取服务列表
curl http://localhost:8080/api/v1/services

# 启动 MiniMax 搜索
curl -X POST http://localhost:8080/api/v1/services/minimax-search/start

# 调用搜索工具
curl -X POST http://localhost:8080/api/v1/services/minimax-search/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"web_search","arguments":{"query":"今天新闻"}}'
```

## 已支持服务

| 服务 | 功能 |
|------|------|
| minimax-search | MiniMax 网络搜索 |
| minimax-image | MiniMax 图像理解 |
| tavily-search | Tavily AI 搜索 |
| exa-search | Exa 神经搜索 |
| github | GitHub 集成 |
| puppeteer | 浏览器自动化 |
| filesystem | 文件系统访问 |

## 配置说明

```yaml
mcp:
  enabled:
    - name: minimax-search
      displayName: "MiniMax 搜索"
      command: "python3"
      args: ["-m", "minimax_mcp.server"]
      env:
        - name: MINIMAX_API_KEY
          valueFrom: env:MINIMAX_API_KEY
        - name: MINIMAX_API_HOST
          value: "https://api.minimaxi.com"
      port: 3001
      enabled: true
```

## 项目结构

```
clawmcp-gateway/
├── gateway.py          # 主程序
├── config.yaml         # MCP 服务配置
├── configs/
│   ├── .env.example  # 环境变量模板
│   └── .env          # 环境变量 (不提交)
└── README.md
```

## License

MIT
