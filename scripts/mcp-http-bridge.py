#!/usr/bin/env python3
"""
Simple MCP to HTTP bridge - Simplified version
"""
import os
import sys
import json
import asyncio
import signal
from aiohttp import web

# 设置环境变量
os.environ.setdefault('MINIMAX_API_KEY', os.getenv('MINIMAX_API_KEY', ''))
os.environ.setdefault('MINIMAX_API_HOST', 'https://api.minimaxi.com')
os.environ.setdefault('MINIMAX_MCP_BASE_PATH', '/tmp/minimax-mcp')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001

# 全局变量
mcp_session = None

async def init_mcp():
    global mcp_session
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    
    print("Initializing MCP...", file=sys.stderr)
    
    # 使用当前进程的环境变量
    env = os.environ.copy()
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'minimax_mcp.server'],
        env=env
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            print("Creating session...", file=sys.stderr)
            session = ClientSession(read, write)
            await asyncio.wait_for(session.initialize(), timeout=30)
            print("MCP initialized!", file=sys.stderr)
            
            # Get tools
            tools = await asyncio.wait_for(session.list_tools(), timeout=30)
            print(f"Found {len(tools.tools)} tools", file=sys.stderr)
            
            mcp_session = session
            
            # Start HTTP server
            app = web.Application()
            
            async def health(request):
                return web.json_response({"status": "ok", "mcp": "connected"})
            
            async def list_tools(request):
                if not mcp_session:
                    return web.json_response({"error": "MCP not connected"}, status=500)
                tools = await mcp_session.list_tools()
                return web.json_response({
                    "tools": [
                        {"name": t.name, "description": t.description}
                        for t in tools.tools
                    ]
                })
            
            async def call_tool(request):
                if not mcp_session:
                    return web.json_response({"error": "MCP not connected"}, status=500)
                
                data = await request.json()
                tool_name = data.get("tool")
                arguments = data.get("arguments", {})
                
                if not tool_name:
                    return web.json_response({"error": "tool is required"}, status=400)
                
                try:
                    result = await asyncio.wait_for(
                        mcp_session.call_tool(tool_name, arguments),
                        timeout=60
                    )
                    return web.json_response({
                        "result": [r.text if hasattr(r, 'text') else str(r) for r in result]
                    })
                except Exception as e:
                    return web.json_response({"error": str(e)}, status=500)
            
            app.router.add_get('/health', health)
            app.router.add_get('/tools', list_tools)
            app.router.add_post('/call', call_tool)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            
            print(f"MCP HTTP bridge started on port {PORT}", file=sys.stderr)
            
            # 保持运行
            await asyncio.Event().wait()
            
    except asyncio.TimeoutError:
        print("MCP initialization timeout", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    # 设置信号处理
    loop = asyncio.new_event_loop()
    loop.run_until_complete(init_mcp())
