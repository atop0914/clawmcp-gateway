#!/usr/bin/env python3
"""
MCP HTTP Bridge - 将 MCP stdio 转为 HTTP
支持完整的 MCP 协议
"""
import os
import sys
import json
import asyncio
import subprocess
import signal
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

import httpx
from aiohttp import web


# ==================== 配置 ====================

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
MCP_COMMAND = os.getenv("MCP_COMMAND", "python3")
MCP_ARGS = os.getenv("MCP_ARGS", "-m minimax_mcp.server").split()


# ==================== MCP 客户端 ====================

@dataclass
class MCPClient:
    """MCP JSON-RPC 客户端"""
    process: subprocess.Popen = field(default=None, repr=False)
    request_id: int = 2
    pending_requests: Dict[int, asyncio.Future] = field(default_factory=dict)
    
    async def start(self):
        """启动 MCP 进程"""
        env = os.environ.copy()
        
        self.process = subprocess.Popen(
            [MCP_COMMAND] + MCP_ARGS,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True
        )
        
        # 启动读取循环
        asyncio.create_task(self._read_loop())
        
        # 初始化
        await self._send_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-bridge", "version": "1.0"}
            }
        })
        
        # 发送 initialized 通知
        await self._send_notification({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        
        print(f"MCP started, PID: {self.process.pid}", file=sys.stderr)
    
    async def _read_loop(self):
        """读取 MCP 响应"""
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                
                data = json.loads(line.decode())
                
                # 处理响应
                if "id" in data:
                    req_id = data["id"]
                    if req_id in self.pending_requests:
                        future = self.pending_requests.pop(req_id)
                        if "result" in data:
                            future.set_result(data["result"])
                        elif "error" in data:
                            future.set_exception(Exception(str(data["error"])))
                
                # 处理通知
                if "method" in data and "id" not in data:
                    print(f"Notification: {data.get('method')}", file=sys.stderr)
                    
            except Exception as e:
                print(f"Read error: {e}", file=sys.stderr)
    
    async def _send_request(self, data: dict) -> Any:
        """发送请求并等待响应"""
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[data["id"]] = future
        
        self.process.stdin.write((json.dumps(data) + "\n").encode())
        self.process.stdin.flush()
        
        return await asyncio.wait_for(future, timeout=30)
    
    async def _send_notification(self, data: dict):
        """发送通知"""
        self.process.stdin.write((json.dumps(data) + "\n").encode())
        self.process.stdin.flush()
    
    async def list_tools(self) -> list:
        """列出所有工具"""
        result = await self._send_request({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/list",
            "params": {}
        })
        self.request_id += 1
        return result.get("tools", [])
    
    async def call_tool(self, name: str, arguments: dict) -> Any:
        """调用工具"""
        result = await self._send_request({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        })
        self.request_id += 1
        return result
    
    async def stop(self):
        """停止 MCP"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()


# ==================== 全局客户端 ====================

mcp_client: Optional[MCPClient] = None


# ==================== HTTP 处理 ====================

async def health(request):
    """健康检查"""
    running = mcp_client and mcp_client.process and mcp_client.process.poll() is None
    return web.json_response({
        "status": "ok" if running else "error",
        "mcp_running": running
    })


async def list_tools(request):
    """列出所有工具"""
    if not mcp_client or mcp_client.process.poll() is not None:
        return web.json_response({"error": "MCP not running"}, status=400)
    
    try:
        tools = await mcp_client.list_tools()
        return web.json_response({
            "success": True,
            "tools": tools
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def call_tool(request):
    """调用工具"""
    if not mcp_client or mcp_client.process.poll() is not None:
        return web.json_response({"error": "MCP not running"}, status=400)
    
    try:
        data = await request.json()
        tool = data.get("tool")
        arguments = data.get("arguments", {})
        
        if not tool:
            return web.json_response({"error": "tool is required"}, status=400)
        
        result = await mcp_client.call_tool(tool, arguments)
        return web.json_response({
            "success": True,
            "result": result
        })
        
    except asyncio.TimeoutError:
        return web.json_response({"error": "Request timeout"}, status=504)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== 主程序 ====================

async def init_mcp():
    """初始化 MCP 客户端"""
    global mcp_client
    
    # 等待环境变量加载
    await asyncio.sleep(1)
    
    mcp_client = MCPClient()
    try:
        await mcp_client.start()
    except Exception as e:
        print(f"Failed to start MCP: {e}", file=sys.stderr)
        sys.exit(1)


async def cleanup(app):
    """清理"""
    if mcp_client:
        await mcp_client.stop()


async def main():
    """主函数"""
    global mcp_client
    
    # 初始化 MCP
    await init_mcp()
    
    # 创建应用
    app = web.Application()
    app.on_cleanup.append(cleanup)
    
    # 路由
    app.router.add_get('/health', health)
    app.router.add_get('/tools', list_tools)
    app.router.add_post('/call', call_tool)
    
    # 启动服务
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', PORT)
    await site.start()
    
    print(f"MCP HTTP Bridge running on http://127.0.0.1:{PORT}", file=sys.stderr)
    
    # 保持运行
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
