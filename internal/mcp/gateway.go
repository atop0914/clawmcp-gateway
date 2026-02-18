package mcp

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"sync"
	"time"
)

// JSONRPCRequest represents a JSON-RPC request
type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      interface{}     `json:"id,omitempty"`
}

// JSONRPCResponse represents a JSON-RPC response
type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *JSONRPCError   `json:"error,omitempty"`
	ID      interface{}     `json:"id,omitempty"`
}

// JSONRPCError represents a JSON-RPC error
type JSONRPCError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

// MCPTool represents an MCP tool definition
type MCPTool struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	InputSchema map[string]interface{} `json:"inputSchema,omitempty"`
	Example     map[string]interface{}  `json:"example,omitempty"`
}

// Gateway manages MCP stdio processes
type Gateway struct {
	processes map[string]*Process
	mu        sync.RWMutex
}

type Process struct {
	Name     string
	Cmd      *exec.Cmd
	Stdin    io.WriteCloser
	Stdout   *bufio.Reader
	Stderr   *bufio.Reader
	ID       int
	mu       sync.Mutex
}

// NewGateway creates a new MCP Gateway
func NewGateway() *Gateway {
	return &Gateway{
		processes: make(map[string]*Process),
	}
}

// StartProcess starts an MCP stdio process
func (g *Gateway) StartProcess(ctx context.Context, name, image string, args []string, env []string) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	
	if _, exists := g.processes[name]; exists {
		return nil // Already running
	}
	
	// 构建命令 - 直接运行 uvx 或使用 Docker
	var cmd *exec.Cmd
	if image == "uvx" || image == "npx" {
		cmdArgs := append([]string{image}, args...)
		cmd = exec.CommandContext(ctx, "uvx", cmdArgs...)
	} else {
		// 使用 Docker 运行
		cmdArgs := []string{"run", "--rm", "-i"}
		for _, e := range env {
			cmdArgs = append(cmdArgs, "-e", e)
		}
		cmdArgs = append(cmdArgs, image)
		cmdArgs = append(cmdArgs, args...)
		cmd = exec.CommandContext(ctx, "docker", cmdArgs...)
	}
	
	cmd.Env = append(cmd.Env, env...)
	cmd.Env = append(cmd.Env, os.Environ()...)
	
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
	
	g.processes[name] = &Process{
		Name:   name,
		Cmd:    cmd,
		Stdin:  stdin,
		Stdout: bufio.NewReader(stdout),
		Stderr: bufio.NewReader(stderr),
		ID:     1,
	}
	
	// 初始化 MCP
	if err := g.initialize(ctx, name); err != nil {
		delete(g.processes, name)
		return fmt.Errorf("failed to initialize MCP: %w", err)
	}
	
	return nil
}

func (g *Gateway) initialize(ctx context.Context, name string) error {
	// 发送 initialize 请求
	req := JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "initialize",
		Params:  json.RawMessage(`{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"clawmcp-gateway","version":"1.0.0"}}`),
		ID:      1,
	}
	
	if err := g.sendRequest(ctx, name, req); err != nil {
		return err
	}
	
	// 读取响应
	_, err := g.readResponse(ctx, name)
	return err
}

// StopProcess stops an MCP process
func (g *Gateway) StopProcess(name string) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	
	p, exists := g.processes[name]
	if !exists {
		return nil
	}
	
	p.Stdin.Close()
	p.Cmd.Wait()
	
	delete(g.processes, name)
	return nil
}

// CallTool calls an MCP tool
func (g *Gateway) CallTool(ctx context.Context, name, toolName string, args map[string]interface{}) (interface{}, error) {
	g.mu.RLock()
	p, exists := g.processes[name]
	g.mu.RUnlock()
	
	if !exists {
		return nil, fmt.Errorf("process %s not running", name)
	}
	
	p.mu.Lock()
	defer p.mu.Unlock()
	
	// 发送 tool call 请求
	params := map[string]interface{}{
		"name": toolName,
		"arguments": args,
	}
	
	req := JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "tools/call",
		Params:  mustMarshalJSON(params),
		ID:      p.ID,
	}
	
	p.ID++
	
	if err := g.sendRequest(ctx, name, req); err != nil {
		return nil, err
	}
	
	resp, err := g.readResponse(ctx, name)
	if err != nil {
		return nil, err
	}
	
	if resp.Error != nil {
		return nil, fmt.Errorf("MCP error: %s", resp.Error.Message)
	}
	
	var result map[string]interface{}
	if err := json.Unmarshal(resp.Result, &result); err != nil {
		return nil, err
	}
	
	return result, nil
}

// ListTools lists available tools
func (g *Gateway) ListTools(ctx context.Context, name string) ([]MCPTool, error) {
	g.mu.RLock()
	_, exists := g.processes[name]
	g.mu.RUnlock()
	
	if !exists {
		return nil, fmt.Errorf("process %s not running", name)
	}
	
	// 发送 tools/list 请求
	req := JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "tools/list",
		ID:      1,
	}
	
	if err := g.sendRequest(ctx, name, req); err != nil {
		return nil, err
	}
	
	resp, err := g.readResponse(ctx, name)
	if err != nil {
		return nil, err
	}
	
	if resp.Error != nil {
		return nil, fmt.Errorf("MCP error: %s", resp.Error.Message)
	}
	
	// 解析 tools 列表
	var result struct {
		Tools []MCPTool `json:"tools"`
	}
	if err := json.Unmarshal(resp.Result, &result); err != nil {
		return nil, err
	}
	
	return result.Tools, nil
}

func (g *Gateway) sendRequest(ctx context.Context, name string, req JSONRPCRequest) error {
	g.mu.RLock()
	p := g.processes[name]
	g.mu.RUnlock()
	
	data, err := json.Marshal(req)
	if err != nil {
		return err
	}
	
	_, err = p.Stdin.Write(append(data, '\n'))
	return err
}

func (g *Gateway) readResponse(ctx context.Context, name string) (*JSONRPCResponse, error) {
	g.mu.RLock()
	p := g.processes[name]
	g.mu.RUnlock()
	
	// 设置超时
	timeout := 30 * time.Second
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-time.After(timeout):
		return nil, fmt.Errorf("timeout waiting for response")
	default:
		data, err := p.Stdout.ReadBytes('\n')
		if err != nil {
			return nil, err
		}
		
		var resp JSONRPCResponse
		if err := json.Unmarshal(data, &resp); err != nil {
			return nil, err
		}
		
		return &resp, nil
	}
}

func mustMarshalJSON(v interface{}) json.RawMessage {
	data, _ := json.Marshal(v)
	return data
}

// HTTPServer 提供 HTTP 接口来调用 MCP
type HTTPServer struct {
	gateway *Gateway
	port    int
}

func NewHTTPServer(port int) *HTTPServer {
	return &HTTPServer{
		gateway: NewGateway(),
		port:    port,
	}
}

func (s *HTTPServer) HandleToolCall(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Tool      string                 `json:"tool"`
		Arguments map[string]interface{} `json:"arguments"`
	}
	
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), 400)
		return
	}
	
	// 这里需要从路径或请求中获取服务名
	// 简化版本，假设只运行一个 MCP 服务
	result, err := s.gateway.CallTool(r.Context(), "default", req.Tool, req.Arguments)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	
	json.NewEncoder(w).Encode(result)
}

func (s *HTTPServer) HandleToolsList(w http.ResponseWriter, r *http.Request) {
	tools, err := s.gateway.ListTools(r.Context(), "default")
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	
	json.NewEncoder(w).Encode(tools)
}

func (s *HTTPServer) Start() error {
	http.HandleFunc("/tools", s.HandleToolsList)
	http.HandleFunc("/call", s.HandleToolCall)
	
	return http.ListenAndServe(fmt.Sprintf(":%d", s.port), nil)
}
