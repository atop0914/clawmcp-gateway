// ClawMCP Gateway Frontend

const API_BASE = '/api/v1';

// Console functions
function log(message, type = 'log') {
    const output = document.getElementById('consoleOutput');
    const time = new Date().toLocaleTimeString();
    const div = document.createElement('div');
    div.className = type;
    div.textContent = `[${time}] ${message}`;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
}

function clearConsole() {
    document.getElementById('consoleOutput').innerHTML = '';
}

function logInfo(msg) { log(msg, 'info'); }
function logError(msg) { log(msg, 'error'); }

// Load services
async function loadServices() {
    try {
        logInfo('正在加载服务列表...');
        const resp = await fetch(`${API_BASE}/services`);
        const data = await resp.json();
        
        if (data.success) {
            document.getElementById('totalCount').textContent = data.data.length;
            renderServices(data.data);
            logInfo(`已加载 ${data.data.length} 个服务`);
        }
    } catch (e) {
        logError(`加载失败: ${e.message}`);
    }
}

// Render services
function renderServices(services) {
    const container = document.getElementById('services');
    container.innerHTML = services.map(svc => `
        <div class="service-card">
            <div class="header">
                <h3>${svc.displayName}</h3>
                <span class="status-badge status-${svc.status}">
                    ${svc.status === 'running' ? '运行中' : '已停止'}
                </span>
            </div>
            <p>${svc.description}</p>
            <div class="actions">
                ${svc.status === 'running' 
                    ? `<button onclick="stopService('${svc.name}')" class="btn btn-danger">
                        <i class="fas fa-stop"></i> 停止
                       </button>`
                    : `<button onclick="startService('${svc.name}')" class="btn btn-success">
                        <i class="fas fa-play"></i> 启动
                       </button>`
                }
                <button onclick="callTool('${svc.name}')" class="btn btn-primary">
                    <i class="fas fa-terminal"></i> 调用
                </button>
            </div>
        </div>
    `).join('');
}

// Start service
async function startService(name) {
    try {
        logInfo(`启动服务: ${name}...`);
        const resp = await fetch(`${API_BASE}/services/${name}/start`, { 
            method: 'POST' 
        });
        const data = await resp.json();
        
        if (data.success) {
            logInfo(`服务 ${name} 已启动`);
            loadServices();
        } else {
            logError(`启动失败: ${data.detail}`);
        }
    } catch (e) {
        logError(`启动失败: ${e.message}`);
    }
}

// Stop service
async function stopService(name) {
    try {
        logInfo(`停止服务: ${name}...`);
        const resp = await fetch(`${API_BASE}/services/${name}/stop`, { 
            method: 'POST' 
        });
        const data = await resp.json();
        
        if (data.success) {
            logInfo(`服务 ${name} 已停止`);
            loadServices();
        } else {
            logError(`停止失败: ${data.detail}`);
        }
    } catch (e) {
        logError(`停止失败: ${e.message}`);
    }
}

// Call tool (demo)
async function callTool(name) {
    const tool = prompt('请输入工具名称:', 'web_search');
    if (!tool) return;
    
    const argsStr = prompt('请输入参数 (JSON格式):', '{"query":"测试"}');
    if (!argsStr) return;
    
    try {
        const args = JSON.parse(argsStr);
        logInfo(`调用 ${name}.${tool}...`);
        
        const resp = await fetch(`${API_BASE}/services/${name}/call`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool, arguments: args })
        });
        
        const data = await resp.json();
        if (data.success) {
            logInfo('调用成功!');
            console.log(data.data);
            alert('调用成功! 查看控制台输出');
        } else {
            logError(`调用失败: ${data.detail}`);
        }
    } catch (e) {
        logError(`调用失败: ${e.message}`);
    }
}

// Health check
async function checkHealth() {
    try {
        const resp = await fetch('/health');
        const data = await resp.json();
        logInfo(`Gateway 状态: ${data.status}`);
    } catch (e) {
        logError(`健康检查失败: ${e.message}`);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadServices();
    checkHealth();
    // Auto refresh every 30s
    setInterval(loadServices, 30000);
});
