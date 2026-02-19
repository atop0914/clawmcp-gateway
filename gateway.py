"""
ClawMCP Gateway - 后端 API
"""
import os
import sys
import json
import asyncio
import subprocess
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yaml


# ==================== 配置 ====================

# 获取脚本所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", os.path.join(BASE_DIR, "configs/config.yaml"))
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))
MCP_DEFAULT_PORT = 3001


# ==================== 数据模型 ====================

@dataclass
class MCPService:
    name: str
    display_name: str
    description: str
    command: str
    args: List[str]
    env: List[Dict[str, str]]
    port: int
    enabled: bool


class ToolCallRequest(BaseModel):
    tool: str
    arguments: dict = {}


# ==================== MCP 服务器 ====================

class MCPServer:
    """MCP HTTP 服务器"""
    
    def __init__(self, port: int = MCP_DEFAULT_PORT):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 2
    
    async def start(self, service: MCPService) -> bool:
        if self.process and self.process.poll() is None:
            return True
        
        try:
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
            
            cmd = [service.command] + service.args
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
            
            await asyncio.sleep(2)
            
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
        if not self.process:
            return
        self.process.stdin.write((json.dumps(data) + "\n").encode())
        self.process.stdin.flush()
    
    async def call_tool(self, tool: str, arguments: dict) -> Any:
        if not self.process or self.process.poll() is not None:
            raise HTTPException(status_code=400, detail="MCP not running")
        
        req_id = self.request_id
        self.request_id += 1
        
        await self._send_request({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}
        })
        
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
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
            self.process = None


# ==================== 配置加载 ====================

def load_config(path: str) -> List[MCPService]:
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

mcp_server = MCPServer()
services_config: List[MCPService] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global services_config
    services_config = load_config(CONFIG_PATH)
    yield
    await mcp_server.stop()


app = FastAPI(
    title="ClawMCP Gateway API",
    description="MCP 服务管理平台 API",
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

# 静态文件
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ==================== API 路由 ====================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "services": len(services_config),
        "mcp_running": mcp_server.process is not None and mcp_server.process.poll() is None
    }


@app.get("/api/v1/services")
async def list_services():
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
    for svc in services_config:
        if svc.name == name:
            return {"success": True, "data": svc}
    raise HTTPException(status_code=404, detail=f"Service {name} not found")


@app.post("/api/v1/services/{name}/start")
async def start_service(name: str):
    for svc in services_config:
        if svc.name == name:
            success = await mcp_server.start(svc)
            if success:
                return {"success": True, "message": f"service {name} started"}
            raise HTTPException(status_code=500, detail=f"Failed to start {name}")
    raise HTTPException(status_code=404, detail=f"Service {name} not found")


@app.post("/api/v1/services/{name}/stop")
async def stop_service(name: str):
    await mcp_server.stop()
    return {"success": True, "message": f"service {name} stopped"}


@app.post("/api/v1/services/{name}/call")
async def call_tool(name: str, request: ToolCallRequest):
    result = await mcp_server.call_tool(request.tool, request.arguments)
    return {"success": True, "data": result}


# ==================== 前端页面 ====================

@app.get("/")
async def web_ui():
    return FileResponse(os.path.join(BASE_DIR, "templates/index.html"))


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
