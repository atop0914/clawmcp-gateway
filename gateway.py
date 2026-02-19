#!/usr/bin/env python3
"""
ClawMCP Gateway - 纯 Python 版本
MCP 服务管理平台
"""
import os
import sys
import json
import asyncio
import subprocess
import signal
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 配置
CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", "./configs/config.yaml")
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))

# 全局状态
mcp_processes: Dict[str, subprocess.Popen] = {}
mcp_sessions: Dict[str, Any] = {}

@dataclass
class MCPServiceConfig:
    name: str
    displayName: str
    description: str
    command: str
    args: List[str]
    env: List[Dict[str, str]]
    port: int
    enabled: bool

class ToolCallRequest(BaseModel):
    tool: str
    arguments: dict = {}

def load_config() -> List[MCPServiceConfig]:
    """加载配置文件"""
    import yaml
    
    if not os.path.exists(CONFIG_PATH):
        # 默认配置
        return []
    
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    
    services = []
    for svc in data.get("mcp", {}).get("enabled", []):
        services.append(MCPServiceConfig(
            name=svc.get("name", ""),
            displayName=svc.get("displayName", svc.get("name", "")),
            description=svc.get("description", ""),
            command=svc.get("command", ""),
            args=svc.get("args", []),
            env=svc.get("env", []),
            port=svc.get("port", 3001),
            enabled=svc.get("enabled", True)
        ))
    
    return services

def get_env_dict(env_list: List[Dict[str, str]]) -> Dict[str, str]:
    """获取环境变量字典"""
    env = os.environ.copy()
    for e in env_list:
        name = e.get("name", "")
        value = e.get("value", "")
        value_from = e.get("valueFrom", "")
        
        if value:
            env[name] = value
        elif value_from and value_from.startswith("env:"):
            key = value_from[4:]
            if key in os.environ:
                env[name] = os.environ[key]
    
    return env

async def start_mcp_service(service: MCPServiceConfig) -> bool:
    """启动 MCP 服务"""
    global mcp_processes, mcp_sessions
    
    if service.name in mcp_processes:
        return True
    
    try:
        # 构建命令
        cmd = [service.command] + service.args
        env = get_env_dict(service.env)
        
        # 启动进程
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True
        )
        
        mcp_processes[service.name] = proc
        
        # 等待启动
        await asyncio.sleep(2)
        
        # 初始化 MCP
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "clawmcp-gateway", "version": "1.0"}
            }
        }
        proc.stdin.write((json.dumps(init) + "\n").encode())
        proc.stdin.flush()
        
        await asyncio.sleep(1)
        
        # 发送 notifications/initialized
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        proc.stdin.write((json.dumps(notif) + "\n").encode())
        proc.stdin.flush()
        
        await asyncio.sleep(1)
        
        return True
        
    except Exception as e:
        print(f"Failed to start {service.name}: {e}")
        return False

async def stop_mcp_service(service_name: str) -> bool:
    """停止 MCP 服务"""
    global mcp_processes
    
    if service_name in mcp_processes:
        try:
            mcp_processes[service_name].terminate()
            mcp_processes[service_name].wait(timeout=5)
        except:
            mcp_processes[service_name].kill()
        del mcp_processes[service_name]
    
    return True

async def call_mcp_tool(service_name: str, tool: str, arguments: dict) -> Any:
    """调用 MCP 工具 - 通过 HTTP 调用"""
    import httpx
    
    # MiniMax MCP 运行在 3001 端口
    url = f"http://localhost:3001/call"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json={"tool": tool, "arguments": arguments})
        if resp.status_code == 200:
            data = resp.json()
            if "result" in data:
                return data["result"]
            elif "error" in data:
                raise HTTPException(status_code=500, detail=str(data["error"]))
        
        raise HTTPException(status_code=500, detail="MCP call failed")

def get_service_status(service: MCPServiceConfig) -> dict:
    """获取服务状态"""
    running = service.name in mcp_processes
    proc = mcp_processes.get(service.name)
    
    status = "stopped"
    if running and proc and proc.poll() is None:
        status = "running"
    
    return {
        "name": service.name,
        "displayName": service.displayName,
        "description": service.description,
        "status": status,
        "port": service.port
    }

# FastAPI 应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时加载配置
    app.state.services = load_config()
    yield
    # 关闭时清理进程
    for name in list(mcp_processes.keys()):
        await stop_mcp_service(name)

app = FastAPI(title="ClawMCP Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "services": len(app.state.services),
        "running": len(mcp_processes)
    }

@app.get("/api/v1/services")
async def list_services():
    services = [get_service_status(svc) for svc in app.state.services]
    return {"success": True, "data": services}

@app.get("/api/v1/services/{name}")
async def get_service(name: str):
    for svc in app.state.services:
        if svc.name == name:
            return {"success": True, "data": get_service_status(svc)}
    raise HTTPException(status_code=404, detail=f"Service {name} not found")

@app.post("/api/v1/services/{name}/start")
async def start_service(name: str):
    for svc in app.state.services:
        if svc.name == name:
            success = await start_mcp_service(svc)
            if success:
                return {"success": True, "message": f"service {name} started"}
            raise HTTPException(status_code=500, detail=f"Failed to start {name}")
    raise HTTPException(status_code=404, detail=f"Service {name} not found")

@app.post("/api/v1/services/{name}/stop")
async def stop_service(name: str):
    success = await stop_mcp_service(name)
    return {"success": True, "message": f"service {name} stopped"}

@app.post("/api/v1/services/{name}/call")
async def call_tool(name: str, request: ToolCallRequest):
    result = await call_mcp_tool(name, request.tool, request.arguments)
    return {"success": True, "data": result}

# Web UI
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
            <p class="text-gray-400 text-lg">MCP 服务管理平台 | Pure Python Edition</p>
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
            <!-- 服务卡片将通过 JS 加载 -->
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
