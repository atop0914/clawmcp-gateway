#!/usr/bin/env python3
"""
ClawMCP Gateway
MCP 服务管理平台 - 纯 Python 实现

架构说明:
- Gateway: FastAPI HTTP 服务，提供 Web UI 和 API
- MCPServer: MCP stdio 转 HTTP 的适配器
"""
import os
import sys
import json
import asyncio
import subprocess
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import yaml


# ==================== 配置 ====================

CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", "./config.yaml")
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))
MCP_DEFAULT_PORT = 3001


# ==================== 数据模型 ====================

@dataclass
class MCPService:
    """MCP 服务配置"""
    name: str
    display_name: str
    description: str
    command: str
    args: List[str]
    env: List[Dict[str, str]]
    port: int
    enabled: bool


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    tool: str
    arguments: dict = {}


# ==================== MCP 服务器 ====================

class MCPServer:
    """MCP HTTP 服务器 - 将 MCP stdio 转为 HTTP"""
    
    def __init__(self, port: int = MCP_DEFAULT_PORT):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 2
    
    async def start(self, service: MCPService) -> bool:
        """启动 MCP 服务"""
        if self.process and self.process.poll() is None:
            return True
        
        try:
            # 构建环境变量
            env = os.environ.copy()
            for e in service.env:
                name = e.get("name", "")
                value = e.get("value", "")
                value_from = e.get("valueFrom", "")
                
                if value:
                    env[name] = value
                elif value_from and value_from.startswith("env:"):
                    key = value_from[4:]
                    if key in os.environ:
                        env[name] = os.environ[key]
            
            # 启动进程
            cmd = [service.command] + service.args
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
            
            # 等待启动
            await asyncio.sleep(2)
            
            # MCP 协议初始化
            await self._send_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "clientInfo": {"name": "clawmcp-gateway", "version": "1.0"}
                }
            })
            
            await asyncio.sleep(1)
            
            # 发送 notifications/initialized
            await self._send_request({
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            })
            
            await asyncio.sleep(1)
            
            return True
            
        except Exception as e:
            print(f"Failed to start MCP: {e}")
            return False
    
    async def _send_request(self, data: dict) -> None:
        """发送 JSON-RPC 请求"""
        if not self.process:
            return
        self.process.stdin.write((json.dumps(data) + "\n").encode())
        self.process.stdin.flush()
    
    async def call_tool(self, tool: str, arguments: dict) -> Any:
        """调用 MCP 工具"""
        if not self.process or self.process.poll() is not None:
            raise HTTPException(status_code=400, detail="MCP not running")
        
        # 发送调用请求
        req_id = self.request_id
        self.request_id += 1
        
        await self._send_request({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}
        })
        
        # 等待响应
        await asyncio.sleep(3)
        
        line = self.process.stdout.readline()
        if line:
            resp = json.loads(line)
            if "result" in resp:
                return resp["result"]
            elif "error" in resp:
                raise HTTPException(status_code=500, detail=str(resp["error"]))
        
        raise HTTPException(status_code=500, detail="No response from MCP")
    
    async def stop(self) -> None:
        """停止 MCP 服务"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None


# ==================== 配置加载 ====================

def load_config(path: str) -> List[MCPService]:
    """加载配置文件"""
    if not os.path.exists(path):
        return []
    
    with open(path) as f:
        data = yaml.safe_load(f)
    
    services = []
    for svc in data.get("mcp", {}).get("enabled", []):
        services.append(MCPService(
            name=svc.get("name", ""),
            display_name=svc.get("displayName", svc.get("name", "")),
            description=svc.get("description", ""),
            command=svc.get("command", "uvx"),
            args=svc.get("args", []),
            env=svc.get("env", []),
            port=svc.get("port", 3001),
            enabled=svc.get("enabled", True)
        ))
    
    return services


# ==================== FastAPI 应用 ====================

# 全局状态
mcp_server = MCPServer()
services_config: List[MCPService] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global services_config
    services_config = load_config(CONFIG_PATH)
    yield
    await mcp_server.stop()


app = FastAPI(
    title="ClawMCP Gateway",
    description="MCP 服务管理平台",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API 路由 ====================

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "services": len(services_config),
        "mcp_running": mcp_server.process is not None and mcp_server.process.poll() is None
    }


@app.get("/api/v1/services")
async def list_services():
    """获取所有服务列表"""
    result = []
    for svc in services_config:
        status = "stopped"
        if svc.enabled and mcp_server.process and mcp_server.process.poll() is None:
            status = "running"
        
        result.append({
            "name": svc.name,
            "displayName": svc.display_name,
            "description": svc.description,
            "status": status,
            "port": svc.port
        })
    
    return {"success": True, "data": result}


@app.get("/api/v1/services/{name}")
async def get_service(name: str):
    """获取单个服务信息"""
    for svc in services_config:
        if svc.name == name:
            return {"success": True, "data": svc}
    raise HTTPException(status_code=404, detail=f"Service {name} not found")


@app.post("/api/v1/services/{name}/start")
async def start_service(name: str):
    """启动服务"""
    for svc in services_config:
        if svc.name == name:
            success = await mcp_server.start(svc)
            if success:
                return {"success": True, "message": f"service {name} started"}
            raise HTTPException(status_code=500, detail=f"Failed to start {name}")
    raise HTTPException(status_code=404, detail=f"Service {name} not found")


@app.post("/api/v1/services/{name}/stop")
async def stop_service(name: str):
    """停止服务"""
    await mcp_server.stop()
    return {"success": True, "message": f"service {name} stopped"}


@app.post("/api/v1/services/{name}/call")
async def call_tool(name: str, request: ToolCallRequest):
    """调用工具"""
    result = await mcp_server.call_tool(request.tool, request.arguments)
    return {"success": True, "data": result}


# ==================== Web UI ====================

WEB_UI = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ClawMCP Gateway</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; }
        .card { background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body class="text-white">
    <div class="container mx-auto px-4 py-8">
        <header class="mb-8 text-center">
            <h1 class="text-5xl font-bold mb-2">
                <i class="fas fa-network-wired text-blue-400 mr-3"></i>ClawMCP Gateway
            </h1>
            <p class="text-gray-400 text-lg">MCP 服务管理平台 | Pure Python</p>
        </header>

        <div class="flex justify-between items-center mb-6">
            <div class="text-gray-400">
                <i class="fas fa-server mr-2"></i>已配置 <span id="totalCount">0</span> 个服务
            </div>
            <button onclick="loadServices()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded transition">
                <i class="fas fa-sync-alt mr-2"></i>刷新
            </button>
        </div>

        <div id="services" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        </div>
    </div>

    <script>
        async function loadServices() {
            try {
                const resp = await fetch('/api/v1/services');
                const data = await resp.json();
                
                document.getElementById('totalCount').textContent = data.data.length;
                
                const container = document.getElementById('services');
                container.innerHTML = data.data.map(svc => `
                    <div class="card rounded-lg p-4">
                        <div class="flex justify-between items-start mb-2">
                            <h3 class="text-xl font-bold">${svc.displayName}</h3>
                            <span class="px-2 py-1 rounded text-sm ${svc.status === 'running' ? 'bg-green-600' : 'bg-gray-600'}">
                                ${svc.status === 'running' ? '运行中' : '已停止'}
                            </span>
                        </div>
                        <p class="text-gray-400 text-sm mb-4">${svc.description}</p>
                        <div class="flex gap-2">
                            ${svc.status === 'running' 
                                ? `<button onclick="stopService('${svc.name}')" class="bg-red-600 hover:bg-red-700 px-3 py-1 rounded text-sm">
                                    <i class="fas fa-stop mr-1"></i>停止
                                </button>`
                                : `<button onclick="startService('${svc.name}')" class="bg-green-600 hover:bg-green-700 px-3 py-1 rounded text-sm">
                                    <i class="fas fa-play mr-1"></i>启动
                                </button>`
                            }
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error(e);
            }
        }

        async function startService(name) {
            await fetch(`/api/v1/services/${name}/start`, { method: 'POST' });
            loadServices();
        }

        async function stopService(name) {
            await fetch(`/api/v1/services/${name}/stop`, { method: 'POST' });
            loadServices();
        }

        loadServices();
    </script>
</body>
</html>
"""

@app.get("/")
async def web_ui():
    return HTMLResponse(WEB_UI)


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
