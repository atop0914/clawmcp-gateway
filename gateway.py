"""
ClawMCP Gateway - 后端 API
MCP 服务管理平台 - 反向代理架构

架构说明:
- Gateway: 唯一对外入口 (127.0.0.1:PORT)
- MCP Services: 仅监听内部端口 (127.0.0.1:internal_port)
- 外部只能通过 Gateway 访问，隐藏内部细节

当前实现: HTTP 转发模式
"""
import os
import json
from contextlib import asynccontextmanager
from typing import Dict, Optional
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml
import httpx


# ==================== 配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", os.path.join(BASE_DIR, "configs/config.yaml"))
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))
INTERNAL_HOST = "127.0.0.1"


# ==================== 数据模型 ====================

@dataclass
class MCPService:
    name: str
    display_name: str
    description: str
    http_port: int  # 内部 HTTP 端口
    enabled: bool


# ==================== MCP 服务管理器 ====================

class MCPManager:
    """MCP 服务管理器 - 通过 HTTP 转发"""
    
    def __init__(self):
        self.services: Dict[str, MCPService] = {}
        self.http_clients: Dict[str, httpx.AsyncClient] = {}
    
    def load_config(self, path: str) -> None:
        """加载服务配置"""
        if not os.path.exists(path):
            return
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        for svc in data.get("mcp", {}).get("enabled", []):
            if svc.get("enabled", True):
                self.services[svc["name"]] = MCPService(
                    name=svc["name"],
                    display_name=svc.get("displayName", svc["name"]),
                    description=svc.get("description", ""),
                    http_port=svc.get("http_port", svc.get("port", 3001)),
                    enabled=True
                )
    
    async def check_service(self, name: str) -> bool:
        """检查服务是否可访问"""
        if name not in self.services:
            return False
        
        svc = self.services[name]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://{INTERNAL_HOST}:{svc.http_port}/health", timeout=3.0)
                return resp.status_code == 200
        except:
            return False
    
    async def call_tool(self, name: str, tool: str, arguments: dict) -> dict:
        """调用 MCP 工具 - HTTP 转发"""
        if name not in self.services:
            raise HTTPException(status_code=404, detail=f"Service {name} not found")
        
        svc = self.services[name]
        
        # 转发到内部 MCP 服务
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"http://{INTERNAL_HOST}:{svc.http_port}/call",
                    json={"tool": tool, "arguments": arguments}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    # 解析 MCP 响应
                    if "result" in data:
                        return data["result"]
                    elif "error" in data:
                        raise HTTPException(status_code=500, detail=str(data["error"]))
                
                raise HTTPException(status_code=500, detail="MCP call failed")
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="MCP request timeout")
        except httpx.ConnectError:
            raise HTTPException(status_code=400, detail=f"Service {name} not running")
    
    def get_status(self, name: str) -> str:
        """获取服务状态"""
        if name not in self.services:
            return "unknown"
        return "running"  # 状态由外部 MCP 服务管理
    
    async def shutdown(self):
        """关闭"""
        for client in self.http_clients.values():
            await client.aclose()


# ==================== FastAPI 应用 ====================

mcp_manager = MCPManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_manager.load_config(CONFIG_PATH)
    yield
    await mcp_manager.shutdown()


app = FastAPI(
    title="ClawMCP Gateway",
    description="MCP 服务管理平台 - 统一入口",
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
    """健康检查"""
    return {
        "status": "healthy",
        "gateway_version": "1.0.0",
        "services_total": len(mcp_manager.services),
        "internal_host": INTERNAL_HOST
    }


# ==================== 服务管理 API ====================

@app.get("/api/v1/services")
async def list_services():
    """获取所有服务列表（隐藏内部端口细节）"""
    result = []
    for name, svc in mcp_manager.services.items():
        # 检查服务是否可达
        is_running = await mcp_manager.check_service(name)
        
        result.append({
            "name": svc.name,
            "displayName": svc.display_name,
            "description": svc.description,
            "status": "running" if is_running else "stopped"
        })
    
    return {"success": True, "data": result}


@app.get("/api/v1/services/{name}")
async def get_service(name: str):
    """获取单个服务信息"""
    if name not in mcp_manager.services:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    svc = mcp_manager.services[name]
    is_running = await mcp_manager.check_service(name)
    
    return {
        "success": True,
        "data": {
            "name": svc.name,
            "displayName": svc.display_name,
            "description": svc.description,
            "status": "running" if is_running else "stopped"
        }
    }


@app.post("/api/v1/services/{name}/start")
async def start_service(name: str):
    """启动服务 - 托管外部 MCP 服务（待实现）"""
    if name not in mcp_manager.services:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    # 当前版本：假设外部 MCP 服务已启动
    # 后续可以实现服务生命周期管理
    is_running = await mcp_manager.check_service(name)
    if is_running:
        return {"success": True, "message": f"service {name} is already running"}
    
    return {"success": False, "message": f"service {name} not running. Please start MCP server first."}


@app.post("/api/v1/services/{name}/stop")
async def stop_service(name: str):
    """停止服务 - 托管外部 MCP 服务（待实现）"""
    return {"success": False, "message": "Service management not implemented yet"}


@app.post("/api/v1/services/{name}/call")
async def call_tool(name: str, request: Request):
    """调用工具 - 核心转发功能"""
    if name not in mcp_manager.services:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    data = await request.json()
    tool = data.get("tool")
    arguments = data.get("arguments", {})
    
    if not tool:
        raise HTTPException(status_code=400, detail="tool is required")
    
    result = await mcp_manager.call_tool(name, tool, arguments)
    return {"success": True, "data": result}


# ==================== 前端页面 ====================

@app.get("/")
async def web_ui():
    return FileResponse(os.path.join(BASE_DIR, "templates/index.html"))


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=INTERNAL_HOST, port=PORT)
