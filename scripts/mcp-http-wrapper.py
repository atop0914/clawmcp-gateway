#!/usr/bin/env python3
"""
MCP HTTP Wrapper - 将 MCP stdio 服务转换为 HTTP 服务
"""
import os
import sys
import json
import asyncio
from typing import Any

# 设置环境变量
os.environ['MINIMAX_API_KEY'] = os.getenv('MINIMAX_API_KEY', '')
os.environ['MINIMAX_API_HOST'] = os.getenv('MINIMAX_API_HOST', 'https://api.minimaxi.com')
os.environ['MINIMAX_MCP_BASE_PATH'] = os.getenv('MINIMAX_MCP_BASE_PATH', '/tmp/minimax-mcp')

from mcp import ClientSession, StdioServer
from mcp.types import Tool, TextContent
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
session = None
server_process = None

async def init_mcp():
    global session, server_process
    
    # 启动 MCP 服务器进程
    server_process = await StdioServer().start()
    
    # 创建客户端会话
    session = ClientSession(server_process)
    await session.initialize()
    
    print("MCP initialized", file=sys.stderr)

@app.on_event("startup")
async def startup():
    await init_mcp()

@app.get("/tools")
async def list_tools():
    if not session:
        return JSONResponse({"error": "MCP not initialized"}, status_code=500)
    
    tools = await session.list_tools()
    return JSONResponse({
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema
            }
            for t in tools.tools
        ]
    })

@app.post("/call")
async def call_tool(request: Request):
    if not session:
        return JSONResponse({"error": "MCP not initialized"}, status_code=500)
    
    body = await request.json()
    tool_name = body.get("tool")
    arguments = body.get("arguments", {})
    
    if not tool_name:
        return JSONResponse({"error": "tool is required"}, status_code=400)
    
    try:
        result = await session.call_tool(tool_name, arguments)
        return JSONResponse({
            "result": [r.text if hasattr(r, 'text') else str(r) for r in result]
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
