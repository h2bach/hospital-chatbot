package main

import (
	"agent/internal/api"
	"agent/internal/infra/llm"
	"agent/internal/infra/store"
	"agent/internal/rag"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
)

var (
	port = flag.String("p", "6689", "The port to connect to host server")
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
	model, err := llm.NewFromEnvironment(ctx)
	if err != nil {
		log.Fatalf("Failed to initialize LLM providers: %s", err)
	}
	transcriber, err := llm.NewFPTSpeechToTextFromEnvironment()
	if err != nil {
		log.Printf("Speech-to-text disabled: %s", err)
	}
	retriever, err := rag.NewClientFromEnvironment()
	if err != nil {
		log.Fatalf("Failed to initialize RAG client: %s", err)
	}

	server := api.NewServer(
		ctx,
		":"+*port,
		store.NewMemorySessionStore(),
		model,
		retriever,
		transcriber,
	)
	server.Run(ctx)
}
