package handler

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"clawmcp-gateway/internal/config"
	"clawmcp-gateway/internal/docker"
)

type Handler struct {
	dockerMgr *docker.Manager
	config    *config.Config
}

func NewHandler(dockerMgr *docker.Manager, cfg *config.Config) *Handler {
	return &Handler{
		dockerMgr: dockerMgr,
		config:    cfg,
	}
}

// APIResponse is the standard API response format
type APIResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
	Message string      `json:"message,omitempty"`
}

// ServiceInfo represents a service in API response
type ServiceInfo struct {
	Name        string         `json:"name"`
	DisplayName string         `json:"displayName"`
	Description string         `json:"description"`
	Status     string         `json:"status"`
	Port       int            `json:"port"`
	Tools      []config.MCPTool `json:"tools,omitempty"`
}

// GetServices returns list of all MCP services
func (h *Handler) GetServices(c *gin.Context) {
	ctx := c.Request.Context()

	services, err := h.dockerMgr.GetServices(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	result := make([]ServiceInfo, 0, len(services))
	for _, svc := range services {
		result = append(result, ServiceInfo{
			Name:        svc.Name,
			DisplayName: svc.DisplayName,
			Description: svc.Description,
			Status:      svc.Status,
			Port:        svc.Port,
			Tools:       svc.Tools,
		})
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Data:    result,
	})
}

// GetService returns a specific service
func (h *Handler) GetService(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	services, err := h.dockerMgr.GetServices(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	for _, svc := range services {
		if svc.Name == svcName {
			c.JSON(http.StatusOK, APIResponse{
				Success: true,
				Data: ServiceInfo{
					Name:        svc.Name,
					DisplayName: svc.DisplayName,
					Description: svc.Description,
					Status:      svc.Status,
					Port:        svc.Port,
					Tools:       svc.Tools,
				},
			})
			return
		}
	}

	c.JSON(http.StatusNotFound, APIResponse{
		Success: false,
		Error:   fmt.Sprintf("service %s not found", svcName),
	})
}

// StartService starts a specific service
func (h *Handler) StartService(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	if err := h.dockerMgr.StartService(ctx, svcName); err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Message: fmt.Sprintf("service %s started", svcName),
	})
}

// StopService stops a specific service
func (h *Handler) StopService(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	if err := h.dockerMgr.StopService(ctx, svcName); err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Message: fmt.Sprintf("service %s stopped", svcName),
	})
}

// RemoveService removes a specific service
func (h *Handler) RemoveService(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	if err := h.dockerMgr.RemoveService(ctx, svcName); err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Message: fmt.Sprintf("service %s removed", svcName),
	})
}

// CallTool calls a specific tool
func (h *Handler) CallTool(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	var req struct {
		Tool      string                 `json:"tool"`
		Arguments map[string]interface{} `json:"arguments"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	result, err := h.dockerMgr.CallTool(ctx, svcName, req.Tool, req.Arguments)
	if err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Data:    result,
	})
}

// GetServiceLogs returns logs for a specific service
func (h *Handler) GetServiceLogs(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	logs, err := h.dockerMgr.GetContainerLogs(ctx, svcName)
	if err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Data:    strings.TrimSpace(logs),
	})
}

// GenerateSkill generates SKILL.md for a service
func (h *Handler) GenerateSkill(c *gin.Context) {
	ctx := c.Request.Context()
	svcName := c.Param("name")

	services, err := h.dockerMgr.GetServices(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, APIResponse{
			Success: false,
			Error:   err.Error(),
		})
		return
	}

	var svc config.MCPService
	for _, s := range services {
		if s.Name == svcName {
			svc = s
			break
		}
	}

	if svc.Name == "" {
		c.JSON(http.StatusNotFound, APIResponse{
			Success: false,
			Error:   fmt.Sprintf("service %s not found", svcName),
		})
		return
	}

	// 生成 SKILL.md
	skill := generateSkillMarkdown(svc, c.Request.Host)

	c.JSON(http.StatusOK, APIResponse{
		Success: true,
		Data:    skill,
	})
}

func generateSkillMarkdown(svc config.MCPService, host string) string {
	var buf strings.Builder

	buf.WriteString(fmt.Sprintf("# %s\n\n", svc.DisplayName))
	buf.WriteString(fmt.Sprintf("%s\n\n", svc.Description))
	buf.WriteString("## Tools\n\n")

	if len(svc.Tools) == 0 {
		buf.WriteString("*No tools available*\n\n")
	} else {
		for _, tool := range svc.Tools {
			buf.WriteString(fmt.Sprintf("### %s\n\n", tool.Name))
			buf.WriteString(fmt.Sprintf("%s\n\n", tool.Description))

			if tool.InputSchema != nil {
				buf.WriteString("**Parameters:**\n\n")
				if props, ok := tool.InputSchema["properties"].(map[string]interface{}); ok {
					for name, prop := range props {
						required := false
						if requiredList, ok := tool.InputSchema["required"].([]interface{}); ok {
							for _, r := range requiredList {
								if r == name {
									required = true
									break
								}
							}
						}
						requiredStr := ""
						if required {
							requiredStr = " (required)"
						}

						buf.WriteString(fmt.Sprintf("- `%s`%s\n", name, requiredStr))
						if propMap, ok := prop.(map[string]interface{}); ok {
							if t, ok := propMap["type"].(string); ok {
								buf.WriteString(fmt.Sprintf("  - Type: %s\n", t))
							}
							if d, ok := propMap["description"].(string); ok {
								buf.WriteString(fmt.Sprintf("  - Description: %s\n", d))
							}
						}
					}
				}
				buf.WriteString("\n")
			}

			if tool.Example != nil {
				buf.WriteString("**Example:**\n\n")
				buf.WriteString("```bash\n")
				exampleJSON, _ := json.MarshalIndent(tool.Example, "", "  ")
				buf.WriteString(fmt.Sprintf("curl -X POST \"http://%s/api/v1/services/%s/call\" \\\n", host, svc.Name))
				buf.WriteString(fmt.Sprintf("  -H \"Content-Type: application/json\" \\\n"))
				buf.WriteString(fmt.Sprintf("  -d '%s'\n", exampleJSON))
				buf.WriteString("```\n\n")
			}
		}
	}

	buf.WriteString("## Usage\n\n")
	buf.WriteString("Call tool:\n")
	buf.WriteString("```bash\n")
	buf.WriteString(fmt.Sprintf("curl -X POST \"http://%s/api/v1/services/%s/call\" \\\n", host, svc.Name))
	buf.WriteString("  -H \"Content-Type: application/json\" \\\n")
	buf.WriteString("  -d '{\"tool\":\"TOOL_NAME\",\"arguments\":{...}}'\n")
	buf.WriteString("```\n")

	return buf.String()
}

// HealthCheck returns health status
func (h *Handler) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"timestamp": time.Now().Format(time.RFC3339),
		"services":  len(h.config.MCP.Enabled),
	})
}

// WebUI serves the web interface
func (h *Handler) WebUI(c *gin.Context) {
	tmpl := `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ClawMCP Gateway</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; }
        .card { background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body class="text-white">
    <div class="container mx-auto px-4 py-8">
        <header class="mb-8 text-center">
            <h1 class="text-5xl font-bold mb-2">
                <i class="fas fa-network-wired text-blue-400 mr-3"></i>ClawMCP Gateway
            </h1>
            <p class="text-gray-400 text-lg">MCP 服务管理平台 | All-in-One MCP Hub</p>
        </header>

        <div class="flex justify-between items-center mb-6">
            <div class="text-gray-400">
                <i class="fas fa-server mr-2"></i>已配置 <span id="totalCount">0</span> 个服务
            </div>
            <button onclick="loadServices()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded transition">
                <i class="fas fa-sync-alt mr-2"></i>刷新
            </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="services">
            <div class="col-span-full text-center py-12">
                <i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i>
                <p class="mt-4 text-gray-400">加载中...</p>
            </div>
        </div>

        <footer class="mt-12 text-center text-gray-500 text-sm">
            <p>ClawMCP Gateway v1.0.0 | <a href="/api/v1/services" class="text-blue-400 hover:underline">API 文档</a></p>
        </footer>
    </div>

    <!-- Skill Modal -->
    <div id="skillModal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-gray-900 rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[80vh] overflow-auto">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold">Skill 文档</h3>
                <button onclick="closeSkillModal()" class="text-gray-400 hover:text-white">
                    <i class="fas fa-times text-xl"></i>
                </button>
            </div>
            <pre id="skillContent" class="bg-gray-800 p-4 rounded overflow-x-auto text-sm"></pre>
            <div class="mt-4 flex gap-2">
                <button onclick="copySkill()" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded">
                    <i class="fas fa-copy mr-2"></i>复制
                </button>
            </div>
        </div>
    </div>

    <!-- Tools Modal -->
    <div id="toolsModal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50">
        <div class="bg-gray-900 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-auto">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold">可用工具</h3>
                <button onclick="closeToolsModal()" class="text-gray-400 hover:text-white">
                    <i class="fas fa-times text-xl"></i>
                </button>
            </div>
            <div id="toolsContent"></div>
        </div>
    </div>

    <script>
        async function loadServices() {
            try {
                const resp = await fetch('/api/v1/services');
                const data = await resp.json();

                if (!data.success) {
                    throw new Error(data.error);
                }

                const services = data.data;
                const container = document.getElementById('services');
                document.getElementById('totalCount').textContent = services.length;

                if (services.length === 0) {
                    container.innerHTML = '<div class="col-span-full text-center py-12 text-gray-400">暂无 MCP 服务，请在配置文件中添加</div>';
                    return;
                }

                container.innerHTML = services.map(svc => {
                    const statusClass = svc.status === 'running' ? 'bg-green-500' : 'bg-red-500';
                    const statusText = svc.status === 'running' ? '运行中' : '已停止';
                    const toolsCount = svc.tools ? svc.tools.length : 0;

                    return '<div class="card rounded-lg p-6">' +
                        '<div class="flex justify-between items-start mb-4">' +
                            '<div class="flex-1">' +
                                '<h3 class="text-xl font-bold">' + (svc.displayName || svc.name) + '</h3>' +
                                '<p class="text-sm text-gray-400 mt-1">' + (svc.description || '') + '</p>' +
                            '</div>' +
                            '<span class="px-3 py-1 rounded-full text-xs font-bold ' + statusClass + ' text-white ml-3">' + statusText + '</span>' +
                        '</div>' +
                        '<div class="mb-4">' +
                            '<span class="text-sm text-gray-500"><i class="fas fa-tools mr-2"></i>' + toolsCount + ' 个工具</span>' +
                            (svc.port ? '<span class="text-sm text-gray-500 ml-4"><i class="fas fa-plug mr-2"></i>端口: ' + svc.port + '</span>' : '') +
                        '</div>' +
                        '<div class="flex flex-wrap gap-2">' +
                            (svc.status !== 'running' ?
                                '<button onclick="startService(\\'' + svc.name + '\\')" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded transition flex-1 min-w-[100px]">' +
                                    '<i class="fas fa-play mr-2"></i>启动' +
                                '</button>' :
                                '<button onclick="stopService(\\'' + svc.name + '\\')" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded transition flex-1 min-w-[100px]">' +
                                    '<i class="fas fa-stop mr-2"></i>停止' +
                                '</button>'
                            ) +
                            '<button onclick="showTools(\\'' + svc.name + '\\')" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded transition">' +
                                '<i class="fas fa-tools mr-2"></i>工具' +
                            '</button>' +
                            '<button onclick="showSkill(\\'' + svc.name + '\\')" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded transition">' +
                                '<i class="fas fa-file-code mr-2"></i>Skill' +
                            '</button>' +
                        '</div>' +
                    '</div>';
                }).join('');
            } catch (err) {
                document.getElementById('services').innerHTML =
                    '<div class="col-span-full text-center py-12 text-red-400">加载失败: ' + err.message + '</div>';
            }
        }

        async function startService(name) {
            try {
                await fetch('/api/v1/services/' + name + '/start', { method: 'POST' });
                loadServices();
            } catch (err) {
                alert('启动失败: ' + err.message);
            }
        }

        async function stopService(name) {
            try {
                await fetch('/api/v1/services/' + name + '/stop', { method: 'POST' });
                loadServices();
            } catch (err) {
                alert('停止失败: ' + err.message);
            }
        }

        async function showTools(name) {
            const resp = await fetch('/api/v1/services/' + name);
            const data = await resp.json();

            if (data.success && data.data.tools && data.data.tools.length > 0) {
                const content = data.data.tools.map(tool => {
                    let params = '';
                    if (tool.inputSchema && tool.inputSchema.properties) {
                        params = Object.entries(tool.inputSchema.properties).map(([key, val]) => {
                            const v = val;
                            const required = tool.inputSchema.required && tool.inputSchema.required.includes(key);
                            return '<li class="ml-4"><code class="text-blue-400">' + key + '</code>' + (required ? ' (必填)' : '') + '</li>';
                        }).join('');
                    }
                    return '<div class="mb-4 p-3 bg-gray-800 rounded">' +
                        '<h4 class="font-bold text-green-400">' + tool.name + '</h4>' +
                        '<p class="text-gray-300 text-sm mt-1">' + (tool.description || '无描述') + '</p>' +
                        (params ? '<ul class="text-sm text-gray-400 mt-2">' + params + '</ul>' : '') +
                    '</div>';
                }).join('');
                document.getElementById('toolsContent').innerHTML = content;
            } else {
                document.getElementById('toolsContent').innerHTML = '<p class="text-gray-400">无可用工具</p>';
            }

            document.getElementById('toolsModal').classList.remove('hidden');
            document.getElementById('toolsModal').classList.add('flex');
        }

        function closeToolsModal() {
            document.getElementById('toolsModal').classList.add('hidden');
            document.getElementById('toolsModal').classList.remove('flex');
        }

        async function showSkill(name) {
            const resp = await fetch('/api/v1/services/' + name + '/skill');
            const data = await resp.json();

            if (data.success) {
                document.getElementById('skillContent').textContent = data.data;
            } else {
                document.getElementById('skillContent').textContent = '生成失败: ' + data.error;
            }

            document.getElementById('skillModal').classList.remove('hidden');
            document.getElementById('skillModal').classList.add('flex');
        }

        function closeSkillModal() {
            document.getElementById('skillModal').classList.add('hidden');
            document.getElementById('skillModal').classList.remove('flex');
        }

        function copySkill() {
            const content = document.getElementById('skillContent').textContent;
            navigator.clipboard.writeText(content);
            alert('已复制到剪贴板!');
        }

        loadServices();
        setInterval(loadServices, 30000);
    </script>
</body>
</html>`

	t, err := template.New("index").Parse(tmpl)
	if err != nil {
		c.String(http.StatusInternalServerError, "Error rendering template: "+err.Error())
		return
	}
	t.Execute(c.Writer, nil)
}
