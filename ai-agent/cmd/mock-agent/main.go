package main

import (
	"agent/internal/agent"
	"agent/internal/domain"
	"agent/internal/infra/llm"
	"agent/internal/mcp"
	"bufio"
	"context"
	"fmt"
	"log"
	"os"
	"flag"
)

var (
	port = flag.String("p", "8080", "The port to connect to local MCP server")
	route = flag.String("r", "/", "The route that host the MCP server")
)

func main() {
	flag.Parse()
	if flag.NArg() > 0 {
		fmt.Println("Error: Too many arguments")
		fmt.Printf("Type: '%s -h' for help.\n", os.Args[0])
		os.Exit(1)
	} 
	if flag.NFlag() < 1 { 
		fmt.Print("Connect to local MCP server at port: ")
		fmt.Scan(port)
		fmt.Print("Connect to local MCP server at route: ")
		fmt.Scan(route)
	}

	ctx := context.Background()
	apiKey := os.Getenv("GEMINI_API_KEY")
	if apiKey == "" {
		fmt.Printf("Error: Require valid GEMINI_API_KEY environment variable.\n")
		os.Exit(1)
	}
	gemini, err := llm.NewGeminiClient(ctx, apiKey)
	if err != nil {
		log.Fatalf("Failed to connect to Gemini: %s", err)
	}
	if (*route)[0] != '/' {
		r := ("/" + *route)
		route = &r
	}

	log.Printf("Client is connecting to MCP server at http://localhost:%s%s\n", *port, *route)
	mcpClient, err := mcp.NewMCPClient(ctx, "http://localhost:" + *port + *route)
	if err != nil {
		log.Printf("Failed to connect to MCP Server: %s\n", err)
		fmt.Printf("Continuing anyways...\n")
		fmt.Println("----------------------------------------------")
	}

	a := agent.NewAgent(gemini, mcpClient)

	agentContext := domain.Context{}
	scanner := bufio.NewScanner(os.Stdin)
	fmt.Print("Prompt: ")
	for scanner.Scan() {
		var prompt string 
		prompt = scanner.Text()

		text, err := a.Call(ctx, prompt, &agentContext)
		if err != nil {
			log.Fatalf("Failed to call Gemini: %s", err)
		}
		fmt.Println("Agent: " + text)
		fmt.Println("----------------------------------------------")
		agentContext.Messages = append(agentContext.Messages, domain.Message{
			Role: domain.AgentRole,
			Content: text,
		})
		fmt.Print("Prompt: ")
	}
}
