package api

import (
	"net/http"
)

func addRoutes(server *Server) {
	mux := http.NewServeMux()

	server.httpServer.Handler = mux
}
