package docker

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"

	"clawmcp-gateway/internal/config"
)

type Manager struct {
	client     *client.Client
	config     *config.Config
	containers map[string]*ContainerInfo
	mu         sync.RWMutex
	running    map[string]*ProcessInfo
	procMu     sync.RWMutex
}

type ContainerInfo struct {
	Name       string
	ID         string
	Status     string
	Port       int
	StartedAt  time.Time
}

type ProcessInfo struct {
	Name   string
	Cmd    *exec.Cmd
	Stdin  io.WriteCloser
	Stdout io.Reader
	Stderr io.Reader
	ID     int
}

func NewManager(cfg *config.Config) (*Manager, error) {
	var dockerClient *client.Client
	var err error

	// 尝试创建 Docker 客户端
	dockerClient, err = client.NewClientWithOpts(
		client.FromEnv,
		client.WithAPIVersionNegotiation(),
	)
	if err != nil {
		fmt.Printf("Docker not available, using process mode: %v\n", err)
		dockerClient = nil
	}

	m := &Manager{
		client:     dockerClient,
		config:     cfg,
		containers: make(map[string]*ContainerInfo),
		running:    make(map[string]*ProcessInfo),
	}

	return m, nil
}

func (m *Manager) StartService(ctx context.Context, svcName string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	var svc *config.MCPService
	for i := range m.config.MCP.Enabled {
		if m.config.MCP.Enabled[i].Name == svcName {
			svc = &m.config.MCP.Enabled[i]
			break
		}
	}

	if svc == nil {
		return fmt.Errorf("service %s not found in config", svcName)
	}

	// 检查是否已经在运行
	m.procMu.RLock()
	if _, ok := m.running[svcName]; ok {
		m.procMu.RUnlock()
		return nil
	}
	m.procMu.RUnlock()

	// 构建环境变量
	env := os.Environ()
	for _, e := range svc.Env {
		value := e.Value
		// 优先使用配置文件中的 value
		if value == "" && e.ValueFrom != "" {
			if strings.HasPrefix(e.ValueFrom, "env:") {
				value = os.Getenv(strings.TrimPrefix(e.ValueFrom, "env:"))
			}
		}
		if value != "" {
			env = append(env, fmt.Sprintf("%s=%s", e.Name, value))
		}
	}

	// 确定运行方式
	var cmd *exec.Cmd
	if svc.Command != "" {
		// 直接运行命令 (uvx 会 fork 子进程后退出，需要保持通信)
		args := []string{svc.Command}
		args = append(args, svc.Args...)
		cmd = exec.CommandContext(ctx, args[0], args[1:]...)
	} else if strings.HasPrefix(svc.Image, "uvx ") {
		// uvx 模式
		parts := strings.Fields(svc.Image)
		cmd = exec.CommandContext(ctx, parts[0], parts[1:]...)
	} else if m.client != nil {
		// Docker 模式 - 启动容器
		return m.startDockerContainer(ctx, svcName, svc)
	} else {
		// 尝试 uvx
		args := []string{"run", "--rm", "-i"}
		for _, e := range svc.Env {
			value := e.Value
			if e.ValueFrom != "" && strings.HasPrefix(e.ValueFrom, "env:") {
				value = os.Getenv(strings.TrimPrefix(e.ValueFrom, "env:"))
			}
			if value != "" {
				args = append(args, "-e", fmt.Sprintf("%s=%s", e.Name, value))
			}
		}
		args = append(args, svc.Image)
		cmd = exec.Command("docker", args...)
	}

	cmd.Env = env

	// 设置进程属性：创建新会话，防止 fork 后父进程退出导致 stdin 关闭
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Setsid: true,
	}

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("failed to create stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start process: %w", err)
	}

	m.procMu.Lock()
	m.running[svcName] = &ProcessInfo{
		Name:   svcName,
		Cmd:    cmd,
		Stdin:  stdin,
		Stdout: stdout,
		Stderr: stderr,
		ID:     1,
	}
	m.procMu.Unlock()

	// 初始化 MCP 协议
	go m.initAndServe(svcName, svc.Port)

	return nil
}

func (m *Manager) startDockerContainer(ctx context.Context, svcName string, svc *config.MCPService) error {
	containerName := fmt.Sprintf("clawmcp-%s", svcName)

	// 检查容器是否已存在
	containers, err := m.client.ContainerList(ctx, types.ContainerListOptions{All: true})
	if err != nil {
		return err
	}

	for _, c := range containers {
		if c.Names[0] == "/"+containerName {
			if c.State == "running" {
				return nil
			}
			return m.client.ContainerStart(ctx, c.ID, types.ContainerStartOptions{})
		}
	}

	// 构建环境变量
	env := []string{}
	for _, e := range svc.Env {
		value := e.Value
		if e.ValueFrom != "" && strings.HasPrefix(e.ValueFrom, "env:") {
			value = os.Getenv(strings.TrimPrefix(e.ValueFrom, "env:"))
		}
		env = append(env, fmt.Sprintf("%s=%s", e.Name, value))
	}

	// 构建命令
	cmd := []string{}
	if svc.Command != "" {
		cmd = append(cmd, svc.Command)
	}
	cmd = append(cmd, svc.Args...)

	hostConfig := &container.HostConfig{
		RestartPolicy: container.RestartPolicy{Name: container.RestartPolicyAlways},
	}

	resp, err := m.client.ContainerCreate(ctx, &container.Config{
		Image:        svc.Image,
		Cmd:          cmd,
		Env:          env,
		Labels:       map[string]string{"clawmcp": "true", "service": svcName},
	}, hostConfig, nil, nil, containerName)
	if err != nil {
		return fmt.Errorf("failed to create container: %w", err)
	}

	return m.client.ContainerStart(ctx, resp.ID, types.ContainerStartOptions{})
}

func (m *Manager) initAndServe(svcName string, port int) {
	m.procMu.RLock()
	p := m.running[svcName]
	m.procMu.RUnlock()

	if p == nil {
		return
	}

	// 发送 initialize 请求
	initReq := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "initialize",
		"params": map[string]interface{}{
			"protocolVersion": "2024-11-05",
			"capabilities":   map[string]interface{}{},
			"clientInfo": map[string]interface{}{
				"name":    "clawmcp-gateway",
				"version": "1.0.0",
			},
		},
		"id": 1,
	}

	data, _ := json.Marshal(initReq)
	p.Stdin.Write(append(data, '\n'))
	p.Stdin.Flush()

	// 等待初始化响应
	time.Sleep(1 * time.Second)

	// 发送 notifications/initialized
	notifReq := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "notifications/initialized",
	}
	data, _ = json.Marshal(notifReq)
	p.Stdin.Write(append(data, '\n'))
	p.Stdin.Flush()

	// 再等待一下让 MCP 服务准备好
	time.Sleep(1 * time.Second)

	// 分配端口
	if port <= 0 {
		port = 3001
	}

	// 启动 HTTP 服务
	mux := http.NewServeMux()
	
	mux.HandleFunc("/tools", func(w http.ResponseWriter, r *http.Request) {
		m.handleToolsList(w, r, svcName)
	})
	
	mux.HandleFunc("/call", func(w http.ResponseWriter, r *http.Request) {
		m.handleToolCall(w, r, svcName)
	})
	
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status":"ok"}`))
	})

	http.ListenAndServe(fmt.Sprintf(":%d", port), mux)
}

func (m *Manager) handleToolsList(w http.ResponseWriter, r *http.Request, svcName string) {
	m.procMu.RLock()
	p := m.running[svcName]
	m.procMu.RUnlock()

	if p == nil {
		http.Error(w, "service not running", 500)
		return
	}

	// 发送 tools/list 请求
	req := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "tools/list",
		"id":      p.ID,
	}
	p.ID++

	data, _ := json.Marshal(req)
	p.Stdin.Write(append(data, '\n'))

	// 读取响应
	buf := make([]byte, 8192)
	n, _ := p.Stdout.Read(buf)

	w.Header().Set("Content-Type", "application/json")
	w.Write(buf[:n])
}

func (m *Manager) handleToolCall(w http.ResponseWriter, r *http.Request, svcName string) {
	m.procMu.RLock()
	p := m.running[svcName]
	m.procMu.RUnlock()

	if p == nil {
		http.Error(w, "service not running", 500)
		return
	}

	var req struct {
		Tool      string                 `json:"tool"`
		Arguments map[string]interface{} `json:"arguments"`
	}
	json.NewDecoder(r.Body).Decode(&req)

	// 发送 tools/call 请求
	rpcReq := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "tools/call",
		"params": map[string]interface{}{
			"name":      req.Tool,
			"arguments": req.Arguments,
		},
		"id": p.ID,
	}
	p.ID++

	data, _ := json.Marshal(rpcReq)
	p.Stdin.Write(append(data, '\n'))

	// 读取响应
	buf := make([]byte, 32768)
	n, _ := p.Stdout.Read(buf)

	w.Header().Set("Content-Type", "application/json")
	w.Write(buf[:n])
}

func (m *Manager) StopService(ctx context.Context, svcName string) error {
	// 停止进程模式
	m.procMu.Lock()
	if p, ok := m.running[svcName]; ok {
		p.Stdin.Close()
		p.Cmd.Wait()
		delete(m.running, svcName)
		m.procMu.Unlock()
		return nil
	}
	m.procMu.Unlock()

	// 停止 Docker 容器
	if m.client != nil {
		containerName := fmt.Sprintf("clawmcp-%s", svcName)
		containers, err := m.client.ContainerList(ctx, types.ContainerListOptions{})
		if err != nil {
			return err
		}
		for _, c := range containers {
			if c.Names[0] == "/"+containerName {
				return m.client.ContainerStop(ctx, c.ID, container.StopOptions{})
			}
		}
	}

	return fmt.Errorf("service %s not found", svcName)
}

func (m *Manager) RemoveService(ctx context.Context, svcName string) error {
	m.StopService(ctx, svcName)

	if m.client != nil {
		containerName := fmt.Sprintf("clawmcp-%s", svcName)
		containers, err := m.client.ContainerList(ctx, types.ContainerListOptions{All: true})
		if err != nil {
			return err
		}
		for _, c := range containers {
			if c.Names[0] == "/"+containerName {
				if c.State == "running" {
					m.client.ContainerStop(ctx, c.ID, container.StopOptions{})
				}
				return m.client.ContainerRemove(ctx, c.ID, types.ContainerRemoveOptions{})
			}
		}
	}

	m.mu.Lock()
	delete(m.containers, svcName)
	m.mu.Unlock()

	return nil
}

func (m *Manager) GetServices(ctx context.Context) ([]config.MCPService, error) {
	result := make([]config.MCPService, 0)

	// 检查进程模式的服务
	m.procMu.RLock()
	for i := range m.config.MCP.Enabled {
		svc := &m.config.MCP.Enabled[i]
		if _, ok := m.running[svc.Name]; ok {
			svc.Status = "running"
		} else {
			svc.Status = "stopped"
		}
		result = append(result, *svc)
	}
	m.procMu.RUnlock()

	// 如果有 Docker，补充检查
	if m.client != nil {
		containers, err := m.client.ContainerList(ctx, types.ContainerListOptions{All: true})
		if err != nil {
			return result, nil
		}

		for i := range result {
			containerName := fmt.Sprintf("clawmcp-%s", result[i].Name)
			for _, c := range containers {
				if c.Names[0] == "/"+containerName {
					result[i].Status = c.State
					if len(c.Ports) > 0 {
						result[i].Port = int(c.Ports[0].PublicPort)
					}
					break
				}
			}
		}
	}

	return result, nil
}

func (m *Manager) CallTool(ctx context.Context, svcName, toolName string, args map[string]interface{}) (interface{}, error) {
	m.procMu.RLock()
	p, ok := m.running[svcName]
	m.procMu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("service %s not running", svcName)
	}

	// 发送 tools/call 请求
	req := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  "tools/call",
		"params": map[string]interface{}{
			"name":      toolName,
			"arguments": args,
		},
		"id": p.ID,
	}
	p.ID++

	data, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}

	_, err = p.Stdin.Write(append(data, '\n'))
	if err != nil {
		return nil, err
	}

	// 读取响应
	buf := make([]byte, 65536)
	n, err := p.Stdout.Read(buf)
	if err != nil && err != io.EOF {
		return nil, err
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(buf[:n], &resp); err != nil {
		return nil, err
	}

	if errMsg, ok := resp["error"].(map[string]interface{}); ok {
		return nil, fmt.Errorf("MCP error: %v", errMsg["message"])
	}

	return resp["result"], nil
}

func (m *Manager) GetContainerLogs(ctx context.Context, svcName string) (string, error) {
	m.procMu.RLock()
	p, ok := m.running[svcName]
	m.procMu.RUnlock()

	if ok && p.Stderr != nil {
		buf := make([]byte, 4096)
		n, _ := p.Stderr.Read(buf)
		return string(buf[:n]), nil
	}

	if m.client != nil {
		containerName := fmt.Sprintf("clawmcp-%s", svcName)
		containers, err := m.client.ContainerList(ctx, types.ContainerListOptions{})
		if err != nil {
			return "", err
		}
		for _, c := range containers {
			if c.Names[0] == "/"+containerName {
				logs, err := m.client.ContainerLogs(ctx, c.ID, types.ContainerLogsOptions{
					ShowStdout: true,
					ShowStderr: true,
					Tail:       "100",
				})
				if err != nil {
					return "", err
				}
				defer logs.Close()
				body, _ := io.ReadAll(logs)
				return string(body), nil
			}
		}
	}

	return "", fmt.Errorf("no logs available for %s", svcName)
}

func (m *Manager) Close() error {
	if m.client != nil {
		return m.client.Close()
	}
	return nil
}
