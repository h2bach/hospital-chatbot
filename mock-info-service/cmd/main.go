package main

import (
	"mock-info-service/internal/api"
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
	server := api.NewServer(
		ctx,
		":" + *port,
	)
	server.Run(ctx)
}

