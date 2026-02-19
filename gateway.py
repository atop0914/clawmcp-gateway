"""
ClawMCP Gateway - 后端 API
MCP 服务管理平台 - 反向代理架构 + 工具注册

架构说明:
- Gateway: 唯一对外入口 (127.0.0.1:PORT)
- MCP Services: 仅监听内部端口
- 工具注册: 预定义每个服务的工具，大模型可据此生成 SKILL.md
"""
import os
import json
from contextlib import asynccontextmanager
from typing import Dict, Optional, List
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yaml
import httpx


# ==================== 配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", os.path.join(BASE_DIR, "configs/config.yaml"))
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))
INTERNAL_HOST = "127.0.0.1"


# ==================== 工具注册表 ====================

TOOL_REGISTRY = {
    "minimax-search": {
        "name": "MiniMax 搜索",
        "description": "基于 MiniMax AI 的网络搜索服务",
        "tools": [
            {
                "name": "web_search",
                "description": "搜索互联网获取最新信息",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "understand_image",
                "description": "分析图片内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "图片URL或base64"},
                        "question": {"type": "string", "description": "关于图片的问题"}
                    },
                    "required": ["image"]
                }
            }
        ]
    },
    "tavily-search": {
        "name": "Tavily AI 搜索",
        "description": "AI 优化的搜索服务",
        "tools": [
            {
                "name": "tavily_search",
                "description": "Tavily 深度搜索",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "max_results": {"type": "integer", "description": "最大结果数"}
                    },
                    "required": ["query"]
                }
            }
        ]
    },
    "exa-search": {
        "name": "Exa 神经搜索",
        "description": "基于 AI 的神经搜索引擎",
        "tools": [
            {
                "name": "exa_search",
                "description": "Exa 神经搜索",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "num_results": {"type": "integer", "description": "结果数量"}
                    },
                    "required": ["query"]
                }
            }
        ]
    },
    "github": {
        "name": "GitHub",
        "description": "GitHub API 集成",
        "tools": [
            {
                "name": "get_pull_requests",
                "description": "获取 Pull Request 列表"
            },
            {
                "name": "search_repositories",
                "description": "搜索代码仓库"
            }
        ]
    },
    "puppeteer": {
        "name": "浏览器自动化",
        "description": "Puppeteer 浏览器控制",
        "tools": [
            {
                "name": "navigate",
                "description": "导航到 URL",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "目标 URL"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "screenshot",
                "description": "截图"
            }
        ]
    },
    "filesystem": {
        "name": "文件系统",
        "description": "本地文件系统访问",
        "tools": [
            {
                "name": "read_file",
                "description": "读取文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "写入文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["path", "content"]
                }
            }
        ]
    }
}


# ==================== 数据模型 ====================

@dataclass
class MCPService:
    name: str
    display_name: str
    description: str
    http_port: int
    enabled: bool


# ==================== MCP 服务管理器 ====================

class MCPManager:
    def __init__(self):
        self.services: Dict[str, MCPService] = {}
    
    def load_config(self, path: str) -> None:
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
        if name not in self.services:
            raise HTTPException(status_code=404, detail=f"Service {name} not found")
        
        svc = self.services[name]
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"http://{INTERNAL_HOST}:{svc.http_port}/call",
                    json={"tool": tool, "arguments": arguments}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if "result" in data:
                        return data["result"]
                    elif "error" in data:
                        raise HTTPException(status_code=500, detail=str(data["error"]))
                
                raise HTTPException(status_code=500, detail="MCP call failed")
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="MCP request timeout")
        except httpx.ConnectError:
            raise HTTPException(status_code=400, detail=f"Service {name} not running")
    
    def get_tools(self, name: str) -> Optional[List[dict]]:
        """获取服务工具列表"""
        return TOOL_REGISTRY.get(name, {}).get("tools")
    
    def get_all_tools(self) -> Dict[str, List[dict]]:
        """获取所有服务的工具"""
        result = {}
        for name in self.services:
            tools = self.get_tools(name)
            if tools:
                result[name] = tools
        return result
    
    def generate_skill(self, name: str) -> Optional[str]:
        """生成 OpenClaw SKILL.md"""
        if name not in TOOL_REGISTRY:
            return None
        
        reg = TOOL_REGISTRY[name]
        tools = reg.get("tools", [])
        
        lines = [
            f"# {reg['name']}",
            "",
            f"_{reg['description']}_",
            "",
            "## 工具",
            ""
        ]
        
        for tool in tools:
            input_schema = tool.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            lines.append(f"### {tool['name']}")
            lines.append("")
            lines.append(f"_{tool['description']}_")
            lines.append("")
            lines.append("**参数:**")
            
            if properties:
                for prop_name, prop_info in properties.items():
                    required_mark = " (必填)" if prop_name in required else ""
                    prop_type = prop_info.get("type", "any")
                    prop_desc = prop_info.get("description", "")
                    lines.append(f"- `{prop_name}` ({prop_type}){required_mark}: {prop_desc}")
            else:
                lines.append("无参数")
            
            lines.append("")
        
        lines.append("---")
        lines.append(f"*由 ClawMCP Gateway 自动生成*")
        
        return "\n".join(lines)


# ==================== FastAPI 应用 ====================

mcp_manager = MCPManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_manager.load_config(CONFIG_PATH)
    yield


app = FastAPI(
    title="ClawMCP Gateway",
    description="MCP 服务管理平台 + 工具注册",
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

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ==================== API 路由 ====================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "gateway_version": "1.0.0",
        "services_total": len(mcp_manager.services),
        "internal_host": INTERNAL_HOST
    }


# ==================== 服务管理 API ====================

@app.get("/api/v1/services")
async def list_services():
    result = []
    for name, svc in mcp_manager.services.items():
        is_running = await mcp_manager.check_service(name)
        
        result.append({
            "name": svc.name,
            "displayName": svc.display_name,
            "description": svc.description,
            "status": "running" if is_running else "stopped",
            "has_tools": name in TOOL_REGISTRY
        })
    
    return {"success": True, "data": result}


@app.get("/api/v1/services/{name}")
async def get_service(name: str):
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
    if name not in mcp_manager.services:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    is_running = await mcp_manager.check_service(name)
    if is_running:
        return {"success": True, "message": f"service {name} is already running"}
    
    return {"success": False, "message": f"service {name} not running"}


@app.post("/api/v1/services/{name}/stop")
async def stop_service(name: str):
    return {"success": False, "message": "Not implemented"}


@app.post("/api/v1/services/{name}/call")
async def call_tool(name: str, request: Request):
    if name not in mcp_manager.services:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    data = await request.json()
    tool = data.get("tool")
    arguments = data.get("arguments", {})
    
    if not tool:
        raise HTTPException(status_code=400, detail="tool is required")
    
    result = await mcp_manager.call_tool(name, tool, arguments)
    return {"success": True, "data": result}


# ==================== 工具 API ====================

@app.get("/api/v1/tools")
async def list_all_tools():
    """获取所有服务的工具列表"""
    return {"success": True, "data": mcp_manager.get_all_tools()}


@app.get("/api/v1/services/{name}/tools")
async def list_service_tools(name: str):
    """获取单个服务的工具列表"""
    tools = mcp_manager.get_tools(name)
    
    if tools is None:
        raise HTTPException(status_code=404, detail=f"Service {name} not found or no tools")
    
    return {"success": True, "data": tools}


@app.get("/api/v1/services/{name}/skill")
async def get_service_skill(name: str):
    """获取服务的 SKILL.md（供大模型使用）"""
    skill = mcp_manager.generate_skill(name)
    
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Service {name} not found")
    
    return PlainTextResponse(skill)


# ==================== 前端页面 ====================

@app.get("/")
async def web_ui():
    return FileResponse(os.path.join(BASE_DIR, "templates/index.html"))


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=INTERNAL_HOST, port=PORT)
