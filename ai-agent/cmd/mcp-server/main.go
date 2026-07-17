package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"

	"agent/internal/mcp"
)

var (
	port = flag.String("p", "8080", "The port to host server")
)

// This binary runs the MCP Server solely.
func main() {
	flag.Parse()
	if flag.NArg() > 0 {
		fmt.Println("Error: Too many arguments")
		fmt.Printf("Type: '%s -h' for help.\n", os.Args[0])
		os.Exit(1)
	} 
	if flag.NFlag() < 1 { 
		fmt.Print("Open MCP server at port: ")
		fmt.Scan(port)
	}

	mcp_server := mcp.NewMCPServer()

	log.Printf("Server is starting at http://localhost:%s\n", *port)
	if err := http.ListenAndServe(":" + *port, mcp_server); err != nil {
		log.Fatalf("Failed to ListenAndServe: %s", err)
	}
	log.Printf("Quit!\n")
}
