package api

import (
	"agent/internal/agent"
	"agent/internal/application"
	"agent/internal/mcp"
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"time"
)

type Server struct {
	addr 				string
	httpServer 			http.Server

	agent				*agent.Agent
	sessionStore 		application.SessionStore
	userStore			application.UserStore
	jwtService			application.JWTService
}

func NewServer(
	ctx				context.Context,
	addr 			string,
	sessionStore	application.SessionStore,
	llm				agent.LLMClient,
) *Server {
	server := Server{
		addr: addr,
		sessionStore: sessionStore,
		userStore: nil,
		jwtService: nil,
	}

	mcpClient, _ := mcp.NewMCPClient(ctx, "http://localhost" + addr + "/mcp")
	server.agent = agent.NewAgent(llm, mcpClient)
	server.httpServer.Addr = addr
	addRoutes(&server)
	return &server
}

func (server *Server) Run(ctx context.Context) {
	ctx, osCancel := signal.NotifyContext(ctx, os.Interrupt)
	defer osCancel()

	log.Printf("Server is starting at http://localhost%s\n", server.addr)
	go func() {
		err := server.httpServer.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP ListenAndServe: %s\n", err)
		}
	}()

	var wg sync.WaitGroup
	wg.Add(1)
	go func(){
		defer wg.Done()
		<-ctx.Done()
		shutdownCtx := context.Background()
		shutdownCtx, cancel := context.WithTimeout(shutdownCtx, time.Second * 10)
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
	server.agent.MCPClient.Disconnect()
}
