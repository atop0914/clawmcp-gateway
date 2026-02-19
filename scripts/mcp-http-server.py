#!/usr/bin/env python3
"""
MCP HTTP Server - 将 MCP stdio 服务转换为 HTTP 服务
"""
import os
import sys
import json
import asyncio
from aiohttp import web

# 环境变量
os.environ.setdefault('MINIMAX_API_KEY', os.getenv('MINIMAX_API_KEY', ''))
os.environ.setdefault('MINIMAX_API_HOST', 'https://api.minimaxi.com')
os.environ.setdefault('MINIMAX_MCP_BASE_PATH', '/tmp/minimax-mcp')

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
req_id = 2

async def main():
    global req_id
    import subprocess
    
    # 启动 MCP
    mcp_proc = subprocess.Popen(
        ['/tmp/mcp-venv/bin/python', '-m', 'minimax_mcp.server'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True
    )
    print(f'MCP PID: {mcp_proc.pid}', file=sys.stderr)
    await asyncio.sleep(2)
    
    # 初始化
    init = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}, 'resources': {}, 'prompts': {}},
            'clientInfo': {'name': 'gateway', 'version': '1.0'}
        }
    }
    mcp_proc.stdin.write((json.dumps(init)+'\n').encode())
    mcp_proc.stdin.flush()
    await asyncio.sleep(1)
    
    notif = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
    mcp_proc.stdin.write((json.dumps(notif)+'\n').encode())
    mcp_proc.stdin.flush()
    print('MCP initialized', file=sys.stderr)
    
    async def health(r):
        return web.json_response({
            'status': 'ok' if mcp_proc.poll() is None else 'error',
            'mcp_running': mcp_proc.poll() is None
        })
    
    async def call(r):
        global req_id
        data = await r.json()
        tool = data.get('tool')
        args = data.get('arguments', {})
        
        if not tool:
            return web.json_response({'error': 'tool is required'}, status=400)
        
        # 发送调用请求
        curr_id = req_id
        req_id += 1
        req = {
            'jsonrpc': '2.0',
            'id': curr_id,
            'method': 'tools/call',
            'params': {'name': tool, 'arguments': args}
        }
        mcp_proc.stdin.write((json.dumps(req)+'\n').encode())
        mcp_proc.stdin.flush()
        
        # 等待响应
        await asyncio.sleep(5)
        line = mcp_proc.stdout.readline()
        
        if line:
            try:
                resp = json.loads(line)
                if 'result' in resp:
                    return web.json_response({'result': resp['result']})
                elif 'error' in resp:
                    return web.json_response({'error': resp['error']}, status=500)
            except:
                pass
        
        return web.json_response({'error': 'timeout'}, status=500)
    
    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_post('/call', call)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f'MCP HTTP bridge started on port {PORT}', file=sys.stderr)
    
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
