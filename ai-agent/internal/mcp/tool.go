package mcp

import (
	"agent/internal/mcp/tools"
	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func bindTools(server *mcp_sdk.Server) {
	mcp_sdk.AddTool(server, &tools.SearchRAGTool, tools.SearchRAGHandler)
	mcp_sdk.AddTool(server, &tools.CheckTimeTool, tools.CheckTimeHandler)
	mcp_sdk.AddTool(server, &tools.HospitalInfoHealthTool, tools.HospitalInfoHealthHandler)
	mcp_sdk.AddTool(server, &tools.HospitalMetaTool, tools.HospitalMetaHandler)
	mcp_sdk.AddTool(server, &tools.SearchDirectoryTool, tools.SearchDirectoryHandler)
	mcp_sdk.AddTool(server, &tools.FacilitiesTool, tools.FacilitiesHandler)
	mcp_sdk.AddTool(server, &tools.OrganizationTool, tools.OrganizationHandler)
	mcp_sdk.AddTool(server, &tools.RoomsTool, tools.RoomsHandler)
	mcp_sdk.AddTool(server, &tools.DoctorsTool, tools.DoctorsHandler)
	mcp_sdk.AddTool(server, &tools.DoctorTool, tools.DoctorHandler)
	mcp_sdk.AddTool(server, &tools.CurrentScheduleTool, tools.CurrentScheduleHandler)
	mcp_sdk.AddTool(server, &tools.DoctorAvailabilityTool, tools.DoctorAvailabilityHandler)
	mcp_sdk.AddTool(server, &tools.SchedulingRulesTool, tools.SchedulingRulesHandler)
	mcp_sdk.AddTool(server, &tools.AssignmentPatternsTool, tools.AssignmentPatternsHandler)
	mcp_sdk.AddTool(server, &tools.DataDictionaryTool, tools.DataDictionaryHandler)
	mcp_sdk.AddTool(server, &tools.SourceRegistryTool, tools.SourceRegistryHandler)
}
