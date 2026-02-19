#!/bin/bash
# MCP HTTP 启动器
# 用法: ./mcp-http-runner.py <port>

export MINIMAX_API_KEY="${MINIMAX_API_KEY}"
export MINIMAX_API_HOST="${MINIMAX_API_HOST}"
export MINIMAX_MCP_BASE_PATH="${MINIMAX_MCP_BASE_PATH}"

PORT=${1:-3001}

cd /tmp/mcp-venv/lib/python3.12/site-packages/minimax_mcp

# 使用 uvicorn 启动 FastMCP 的 SSE 服务器
python -c "
import sys
import asyncio
from server import mcp

async def main():
    # 使用 uvicorn 运行 SSE
    import uvicorn
    config = uvicorn.Config(
        mcp.streamable_http_app(),
        host='0.0.0.0',
        port=$PORT,
        log_level='warning'
    )
    server = uvicorn.Server(config)
    await server.serve()

asyncio.run(main())
" 2>&1
