package main

import (
	"agent/internal/api"
	"agent/internal/infra/llm"
	"agent/internal/infra/store"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
)

var (
	port = flag.String("p", "8080", "The port to connect to host server")
)

// This binary hosts MCP Server at route '/mcp'
func main() {
	flag.Parse()
	if flag.NArg() > 0 {
		fmt.Println("Error: Too many arguments")
		fmt.Printf("Type: '%s -h' for help.\n", os.Args[0])
		os.Exit(1)
	} 
	if flag.NFlag() < 1 { 
		fmt.Print("Host server at port: ")
		fmt.Scan(port)
	}

	ctx := context.Background()
	gemini, err := llm.NewGeminiClient(ctx, os.Getenv("GEMINI_API_KEY"))
	if err != nil {
		log.Fatalf("Failed to connect to Gemini: %s", err)
	}

	server := api.NewServer(
		ctx,
		":" + *port,
		store.NewMockSessionStore(),
		gemini,
	)
	server.Run(ctx)
}
