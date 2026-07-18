package agent

import (
	"agent/internal/domain"
	"fmt"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func normalizeAccessRole(value string) domain.AccessRole {
	return domain.GuestAccessRole
}

// NormalizeRole is used by the HTTP boundary before a request reaches the agent.
func NormalizeRole(value string) domain.AccessRole { return normalizeAccessRole(value) }

func toolsForRole(all []mcp_sdk.Tool, role domain.AccessRole) []mcp_sdk.Tool {
	allowed := roleToolNames(role)
	result := make([]mcp_sdk.Tool, 0, len(all))
	for _, tool := range all {
		if allowed[tool.Name] {
			result = append(result, tool)
		}
	}
	return result
}

func roleToolNames(role domain.AccessRole) map[string]bool {
	// Tất cả công cụ đều chỉ đọc dữ liệu công khai; không có hồ sơ người bệnh
	// hay thao tác tạo/hủy lịch, nên mọi vai trò dùng cùng một tập công cụ.
	public := map[string]bool{}
	for _, name := range []string{
		"checkTime", "hospitalInfoHealth", "getHospitalDatasetMeta",
		"searchHospitalDirectory", "listHospitalFacilities", "getHospitalOrganization",
		"listHospitalRooms", "searchHanoiHeartDoctors", "getHanoiHeartDoctor",
		"listCurrentDoctorSchedule", "getDoctorAvailability", "getSchedulingRules",
		"getObservedAssignmentPatterns", "getScheduleDataDictionary", "getScheduleSourceRegistry",
		"searchHospitalKnowledge", "expandHospitalKnowledgeContext", "getHospitalKnowledgeCatalog",
	} {
		public[name] = true
	}
	return public
}

func ensureToolAllowed(role domain.AccessRole, toolName string) error {
	if !roleToolNames(role)[toolName] {
		return fmt.Errorf("tool %q is not available for role %s", toolName, role)
	}
	return nil
}
