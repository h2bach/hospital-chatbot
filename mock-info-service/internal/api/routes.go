package api

import (
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

	fs := http.FileServer(http.Dir(resolveStaticDir()))



	server.httpServer.Handler = mux
}
