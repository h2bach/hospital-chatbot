package api

import (
	"agent/internal/agent"
	"agent/internal/application"
	"agent/internal/mcp"
	"agent/internal/rag"
	"context"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"time"
)

type Server struct {
	addr       string
	httpServer http.Server

	agent        *agent.Agent
	sessionStore application.SessionStore
	userStore    application.UserStore
	jwtService   application.JWTService
}

func NewServer(
	ctx context.Context,
	addr string,
	sessionStore application.SessionStore,
	llm agent.LLMClient,
	retriever rag.Retriever,
) *Server {
	server := Server{
		addr:         addr,
		sessionStore: sessionStore,
		userStore:    nil,
		jwtService:   nil,
	}

	mcpURL := os.Getenv("MCP_SERVICE_URL")
	if mcpURL == "" {
		mcpURL = "http://localhost" + addr + "/mcp"
	}
	mcpClient := mcp.NewDeferredMCPClient(mcpURL)
	server.agent = agent.NewAgent(llm, mcpClient, retriever)
	server.httpServer.Addr = addr
	addRoutes(&server)
	return &server
}

func (server *Server) Run(ctx context.Context) {
	ctx, osCancel := signal.NotifyContext(ctx, os.Interrupt)
	defer osCancel()

	log.Printf("Server is starting at http://localhost%s\n", server.addr)
	listener, err := net.Listen("tcp", server.addr)
	if err != nil {
		log.Fatalf("HTTP listen: %s\n", err)
	}
	go func() {
		err := server.httpServer.Serve(listener)
		if err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP serve: %s\n", err)
		}
	}()
	if server.agent != nil && server.agent.MCPClient != nil {
		server.agent.MCPClient.Retry(ctx)
	}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		<-ctx.Done()
		shutdownCtx := context.Background()
		shutdownCtx, cancel := context.WithTimeout(shutdownCtx, time.Second*10)
		defer cancel()

		go server.Shutdown()
		err := server.httpServer.Shutdown(shutdownCtx)
		if err != nil {
			log.Fatalf("HTTP Shutdown: %s\n", err)
		}
	}()
	wg.Wait()
}

func (server *Server) Shutdown() {
	if server.agent != nil && server.agent.MCPClient != nil {
		server.agent.MCPClient.Disconnect()
	}
}
