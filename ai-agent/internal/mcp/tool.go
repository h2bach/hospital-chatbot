package mcp

import (
	"agent/internal/mcp/tools"
	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func bindTools(server *mcp_sdk.Server) {
	mcp_sdk.AddTool(server, &tools.CheckTimeTool, tools.CheckTimeHandler)

	// Mock info service tools
	mcp_sdk.AddTool(server, &tools.HealthTool, tools.MockInfoHealthHandler)
	mcp_sdk.AddTool(server, &tools.ListCollectionsTool, tools.ListCollectionsHandler)
	mcp_sdk.AddTool(server, &tools.ListRecordsTool, tools.ListRecordsHandler)
	mcp_sdk.AddTool(server, &tools.GetRecordTool, tools.GetRecordHandler)
	mcp_sdk.AddTool(server, &tools.CreateRecordTool, tools.CreateRecordHandler)
	mcp_sdk.AddTool(server, &tools.UpdateRecordTool, tools.UpdateRecordHandler)
	mcp_sdk.AddTool(server, &tools.DeleteRecordTool, tools.DeleteRecordHandler)
	mcp_sdk.AddTool(server, &tools.SearchInfoTool, tools.SearchInfoHandler)
	mcp_sdk.AddTool(server, &tools.AvailableSlotsTool, tools.AvailableSlotsHandler)
	mcp_sdk.AddTool(server, &tools.CreateAppointmentTool, tools.CreateAppointmentHandler)
	mcp_sdk.AddTool(server, &tools.CancelAppointmentTool, tools.CancelAppointmentHandler)
	mcp_sdk.AddTool(server, &tools.VerifyPatientTool, tools.VerifyPatientHandler)
}
