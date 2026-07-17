package api

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"time"

	"mock-info-service/internal/store"
)

type Server struct {
	addr       string
	httpServer http.Server
	store      *store.JSONStore
}

func NewServer(addr string, dataStore *store.JSONStore) *Server {
	server := &Server{addr: addr, store: dataStore}
	server.httpServer.Addr = addr
	server.addRoutes()
	return server
}

func (server *Server) Handler() http.Handler { return server.httpServer.Handler }

func (server *Server) Run(ctx context.Context) error {
	ctx, cancelSignal := signal.NotifyContext(ctx, os.Interrupt)
	defer cancelSignal()

	log.Printf("Mock Info REST API listening at http://localhost%s", server.addr)
	errCh := make(chan error, 1)
	go func() { errCh <- server.httpServer.ListenAndServe() }()

	select {
	case err := <-errCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		return server.httpServer.Shutdown(shutdownCtx)
	}
}
