package api

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"time"

	"hospital-info-service/internal/data"
)

type Server struct {
	addr       string
	httpServer http.Server
	store      *data.Store
}

func NewServer(addr string, store *data.Store) *Server {
	server := &Server{addr: addr, store: store}
	server.httpServer.Addr = addr
	server.addRoutes()
	return server
}

func (s *Server) Handler() http.Handler { return s.httpServer.Handler }

func (s *Server) Run(ctx context.Context) error {
	ctx, stop := signal.NotifyContext(ctx, os.Interrupt)
	defer stop()
	log.Printf("Hanoi Heart Hospital public information API listening at http://localhost%s", s.addr)
	errCh := make(chan error, 1)
	go func() { errCh <- s.httpServer.ListenAndServe() }()
	select {
	case err := <-errCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
		return nil
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		return s.httpServer.Shutdown(shutdownCtx)
	}
}
