#!/usr/bin/env python3
"""
Simple MCP to HTTP bridge using asyncio
"""
import os
import sys
import json
import asyncio
from aiohttp import web

# 设置环境变量 - 确保传递给子进程
env = os.environ.copy()
env['MINIMAX_API_KEY'] = env.get('MINIMAX_API_KEY', '')
env['MINIMAX_API_HOST'] = env.get('MINIMAX_API_HOST', 'https://api.minimaxi.com')
env['MINIMAX_MCP_BASE_PATH'] = env.get('MINIMAX_MCP_BASE_PATH', '/tmp/minimax-mcp')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001

async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    
    # 启动服务器进程 - 使用 async with，并传递环境变量
    server_params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'minimax_mcp.server'],
        env=env
    )
    async with stdio_client(server_params) as (read, write):
        # 创建客户端会话
        session = ClientSession(read, write)
        await session.initialize()
        
        print("MCP initialized", file=sys.stderr)
        
        # 获取工具列表
        tools_result = await session.list_tools()
        print(f"Found {len(tools_result.tools)} tools", file=sys.stderr)
        
        async def list_tools(request):
            return web.json_response({
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema
                    }
                    for t in tools_result.tools
                ]
            })
        
        async def call_tool(request):
            data = await request.json()
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                return web.json_response({"error": "tool is required"}, status=400)
            
            try:
                result = await session.call_tool(tool_name, arguments)
                return web.json_response({
                    "result": [r.text if hasattr(r, 'text') else str(r) for r in result]
                })
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        
        async def health(request):
            return web.json_response({"status": "ok"})
        
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_get('/tools', list_tools)
        app.router.add_post('/call', call_tool)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        print(f"MCP HTTP bridge started on port {PORT}", file=sys.stderr)
        
        # 保持运行 - 使用一个永远不会完成的任务
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
