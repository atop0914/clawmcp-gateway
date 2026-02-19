"""
ClawMCP Gateway - MCP 服务管理平台
自动启动 MCP 服务 + 提供工具元数据（让大模型自己生成 SKILL）
"""
import os
import sys
import json
import asyncio
import subprocess
import signal
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from aiohttp import web
import yaml


# ==================== 配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("CLAWMCP_CONFIG", os.path.join(BASE_DIR, "configs/config.yaml"))
PORT = int(os.getenv("CLAWMCP_PORT", "8080"))
INTERNAL_HOST = "0.0.0.0"


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


@dataclass
class RunningMCP:
    process: subprocess.Popen
    port: int
    started_at: float
    request_id: int = 2


# ==================== MCP 管理器 ====================

class MCPManager:
    """MCP 服务管理器 - 自动启动/停止"""
    
    def __init__(self):
        self.config: Dict[str, MCPService] = {}
        self.running: Dict[str, RunningMCP] = {}
    
    def load_config(self, path: str) -> None:
        """加载配置"""
        if not os.path.exists(path):
            print(f"Config not found: {path}")
            return
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        self.config.clear()
        for svc in data.get("mcp", {}).get("enabled", []):
            if svc.get("enabled", True):
                self.config[svc["name"]] = MCPService(
                    name=svc["name"],
                    display_name=svc.get("displayName", svc["name"]),
                    description=svc.get("description", ""),
                    command=svc.get("command", "python3"),
                    args=svc.get("args", []),
                    env=svc.get("env", []),
                    port=svc.get("port", 3001),
                    enabled=True
                )
        
        print(f"Loaded {len(self.config)} services")
    
    def _build_env(self, svc: MCPService) -> dict:
        """构建环境变量"""
        env = os.environ.copy()
        for e in svc.env:
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
    
    async def start_service(self, name: str) -> bool:
        """启动 MCP 服务"""
        if name not in self.config:
            return False
        
        # 已运行
        if name in self.running:
            proc = self.running[name].process
            if proc.poll() is None:
                return True
        
        svc = self.config[name]
        
        try:
            # 构建命令
            cmd = [svc.command] + svc.args
            env = self._build_env(svc)
            
            # 启动进程
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
            
            self.running[name] = RunningMCP(
                process=proc,
                port=svc.port,
                started_at=time.time()
            )
            
            # 等待启动
            await asyncio.sleep(5)
            
            # MCP 初始化
            await self._send(name, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "gateway", "version": "1.0"}
                }
            })
            
            await asyncio.sleep(1)
            
            # notifications/initialized
            await self._send(name, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            })
            
            print(f"Started {name} on port {svc.port}")
            return True
            
        except Exception as e:
            print(f"Failed to start {name}: {e}")
            return False
    
    async def _send(self, name: str, data: dict) -> None:
        if name not in self.running:
            return
        proc = self.running[name].process
        proc.stdin.write((json.dumps(data) + "\n").encode())
        proc.stdin.flush()
    
    async def stop_service(self, name: str) -> bool:
        """停止 MCP 服务"""
        if name not in self.running:
            return True
        
        proc = self.running[name].process
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()
        
        del self.running[name]
        print(f"Stopped {name}")
        return True
    
    async def stop_all(self, app=None) -> None:
        """停止所有服务"""
        for name in list(self.running.keys()):
            await self.stop_service(name)
    
    def get_status(self, name: str) -> str:
        """获取状态"""
        if name not in self.config:
            return "unknown"
        if name not in self.running:
            return "stopped"
        return "running" if self.running[name].process.poll() is None else "stopped"
    
    async def list_tools(self, name: str) -> List[dict]:
        """获取工具列表"""
        if name not in self.running:
            return []
        
        running = self.running[name]
        
        await self._send(name, {
            "jsonrpc": "2.0",
            "id": running.request_id,
            "method": "tools/list",
            "params": {}
        })
        running.request_id += 1
        
        await asyncio.sleep(2)
        
        try:
            line = running.process.stdout.readline()
            if line:
                resp = json.loads(line)
                return resp.get("result", {}).get("tools", [])
        except:
            pass
        
        return []
    
    async def call_tool(self, name: str, tool: str, arguments: dict) -> dict:
        """调用工具"""
        if name not in self.running:
            raise web.HTTPBadRequest(text=f"Service {name} not running")
        
        running = self.running[name]
        
        await self._send(name, {
            "jsonrpc": "2.0",
            "id": running.request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}
        })
        running.request_id += 1
        
        await asyncio.sleep(5)
        
        line = running.process.stdout.readline()
        if line:
            resp = json.loads(line)
            if "result" in resp:
                return resp["result"]
            if "error" in resp:
                raise web.HTTPInternalServerError(text=str(resp["error"]))
        
        raise web.HTTPInternalServerError(text="No response from MCP")
    
    async def auto_start(self) -> None:
        """自动启动所有启用的服务"""
        for name, svc in self.config.items():
            if svc.enabled:
                await self.start_service(name)


# ==================== 全局管理器 ====================

manager = MCPManager()


# ==================== 请求处理 ====================

async def health(request):
    """健康检查"""
    running = sum(1 for name in manager.config if manager.get_status(name) == "running")
    
    return web.json_response({
        "status": "healthy",
        "version": "1.0.0",
        "services_total": len(manager.config),
        "services_running": running
    })


async def list_services(request):
    """获取所有服务"""
    result = []
    for name, svc in manager.config.items():
        status = manager.get_status(name)
        
        result.append({
            "name": name,
            "displayName": svc.display_name,
            "description": svc.description,
            "status": status,
            "port": svc.port if status == "running" else None
        })
    
    return web.json_response({"services": result})


async def get_service(request):
    """获取服务详情"""
    name = request.match_info['name']
    
    if name not in manager.config:
        raise web.HTTPNotFound(text=f"Service {name} not found")
    
    svc = manager.config[name]
    status = manager.get_status(name)
    
    # 获取工具列表
    tools = []
    if status == "running":
        tools = await manager.list_tools(name)
    
    return web.json_response({
        "name": name,
        "displayName": svc.display_name,
        "description": svc.description,
        "status": status,
        "tools": tools
    })


async def start_service(request):
    """启动服务"""
    name = request.match_info['name']
    
    if name not in manager.config:
        raise web.HTTPNotFound(text=f"Service {name} not found")
    
    success = await manager.start_service(name)
    
    if success:
        return web.json_response({"success": True, "message": f"{name} started"})
    
    raise web.HTTPInternalServerError(text=f"Failed to start {name}")


async def stop_service(request):
    """停止服务"""
    name = request.match_info['name']
    
    await manager.stop_service(name)
    return web.json_response({"success": True, "message": f"{name} stopped"})


async def call_tool(request):
    """调用工具"""
    name = request.match_info['name']
    
    if name not in manager.config:
        raise web.HTTPNotFound(text=f"Service {name} not found")
    
    try:
        data = await request.json()
    except:
        raise web.HTTPBadRequest(text="Invalid JSON")
    
    tool = data.get("tool")
    arguments = data.get("arguments", {})
    
    if not tool:
        raise web.HTTPBadRequest(text="tool is required")
    
    result = await manager.call_tool(name, tool, arguments)
    return web.json_response({"success": True, "result": result})


async def web_ui(request):
    return web.FileResponse(os.path.join(BASE_DIR, "templates/index.html"))


# ==================== 启动 ====================

async def init(app):
    """初始化"""
    manager.load_config(CONFIG_PATH)
    await manager.auto_start()  # 自动启动所有服务


app = web.Application()
app.on_startup.append(init)
app.on_cleanup.append(manager.stop_all)

# 路由
app.router.add_get('/health', health)
app.router.add_get('/api/v1/services', list_services)
app.router.add_get('/api/v1/services/{name}', get_service)
app.router.add_post('/api/v1/services/{name}/start', start_service)
app.router.add_post('/api/v1/services/{name}/stop', stop_service)
app.router.add_post('/api/v1/services/{name}/call', call_tool)
app.router.add_get('/', web_ui)

# 静态文件
app.router.add_get('/static/{path:.*}', lambda r: web.FileResponse(os.path.join(BASE_DIR, "static", r.match_info['path'])))


if __name__ == "__main__":
    print(f"Starting ClawMCP Gateway on http://{INTERNAL_HOST}:{PORT}")
    web.run_app(app, host=INTERNAL_HOST, port=PORT, access_log=False)
