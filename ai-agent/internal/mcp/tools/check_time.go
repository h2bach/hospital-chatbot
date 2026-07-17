package tools

import (
	"context"
	"errors"
	"time"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

/******************\
* DEVELOPMENT TOOL *
\******************/

var CheckTimeTool = mcp_sdk.Tool{
	Name: "checkTime",
	Description: "get the time at the current moment in hanoi, nyc, beijing",
}

type CheckTimeInput struct {
	City string `json:"city" jsonschema:"hanoi, nyc or beijing; default if empty: hanoi"`
}

type CheckTimeOutput struct {
	Time time.Time `json:"time" jsonschema:"time output of hanoi, nyc or beijing"`
}

func CheckTimeHandler(ctx context.Context, request *mcp_sdk.CallToolRequest, input CheckTimeInput) (
	*mcp_sdk.CallToolResult,
	CheckTimeOutput,
	error,
) {
	now := time.Now()
	var loc *time.Location
	var locString string

	switch input.City {
	case "hanoi":
		locString = "Asia/Ho_Chi_Minh"
	case "nyc":
		locString = "America/New_York"
	case "beijing":
		locString = "Asia/Shanghai"
	case "":
		locString = "Asia/Ho_Chi_Minh"
	default:
		return nil, CheckTimeOutput{}, errors.New("undetected city")
	}

	loc, err := time.LoadLocation(locString)
	if err != nil {
		return nil, CheckTimeOutput{}, err
	}
	now = now.In(loc)

	return nil, CheckTimeOutput{ now }, nil
}
