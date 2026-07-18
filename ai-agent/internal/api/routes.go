package api

import (
	"agent/internal/mcp"
	"agent/internal/rag"
	"log"
	"net/http"
	"os"
)

func resolveStaticDir() string {
	if configuredDir := os.Getenv("AGENT_STATIC_DIR"); configuredDir != "" {
		return configuredDir
	}
	log.Fatalf("Error: AGENT_STATIC_DIR not configured in environment variables\n")
	return ""
}

func addRoutes(server *Server) {
	mux := http.NewServeMux()

	var knowledge rag.KnowledgeProvider
	if server.agent != nil {
		knowledge, _ = server.agent.Retriever.(rag.KnowledgeProvider)
	}
	mux.Handle("/mcp", mcp.NewMCPServer(knowledge))
	mux.HandleFunc("GET /health", server.Health)

	mux.HandleFunc("GET /c", server.GetAllSessions)
	mux.HandleFunc("GET /c/{id}", server.GetSession)
	mux.HandleFunc("POST /c", server.PostNewSession)
	mux.HandleFunc("POST /c/{id}", server.PostMessage)
	mux.HandleFunc("POST /c/{id}/stream", server.PostMessageStream)
	mux.HandleFunc("DELETE /c/{id}", server.DeleteSession)
	mux.HandleFunc("POST /api/stt", server.TranscribeAudio)

	// Keep the API and MCP routes above more specific than this static fallback.
	// Serving the complete directory also exposes Vite public assets at the root.
	fs := http.FileServer(http.Dir(resolveStaticDir()))
	mux.Handle("/", fs)

	server.httpServer.Handler = mux
}
