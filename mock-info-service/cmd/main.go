package main

import (
	"context"
	"flag"
	"log"

	"mock-info-service/internal/api"
	"mock-info-service/internal/store"
)

func main() {
	port := flag.String("port", "8080", "HTTP port")
	data := flag.String("data", "../mock-data/output", "Directory containing JSON datasets")
	flag.Parse()

	dataStore, err := store.Load(*data)
	if err != nil { log.Fatalf("load mock data: %v", err) }
	server := api.NewServer(":"+*port, dataStore)
	if err := server.Run(context.Background()); err != nil { log.Fatalf("server: %v", err) }
}
