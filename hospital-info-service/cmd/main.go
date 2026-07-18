package main

import (
	"context"
	"flag"
	"log"
	"time"

	"hospital-info-service/internal/api"
	"hospital-info-service/internal/data"
)

func main() {
	port := flag.String("port", "8080", "HTTP port")
	dataDir := flag.String("data", "../hospital-data", "Directory containing curated hospital datasets")
	flag.Parse()

	store, err := data.Load(*dataDir)
	if err != nil {
		log.Fatalf("load hospital data: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	store.StartWatcher(ctx, 300*time.Millisecond)
	server := api.NewServer(":"+*port, store)
	if err := server.Run(ctx); err != nil {
		log.Fatalf("server: %v", err)
	}
}
