package agent

import (
	"agent/internal/domain"
	"fmt"
	"strings"

	mcp_sdk "github.com/modelcontextprotocol/go-sdk/mcp"
)

func normalizeAccessRole(value string) domain.AccessRole {
	switch domain.AccessRole(strings.ToUpper(strings.TrimSpace(value))) {
	case domain.PatientAccessRole:
		return domain.PatientAccessRole
	case domain.DoctorAccessRole:
		return domain.DoctorAccessRole
	case domain.AdminAccessRole:
		return domain.AdminAccessRole
	default:
		return domain.GuestAccessRole
	}
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
	guest := map[string]bool{
		"checkTime": true, "createPlan": true, "mockInfoHealth": true,
		"searchInfo": true, "searchHospitalKnowledge": true, "getHospitalInfo": true,
		"getHospitalHours": true, "getEmergencyInfo": true, "listDoctors": true,
		"getDoctorSchedules": true, "listDepartments": true, "listMedicalServices": true,
		"getMedicalService": true, "getServicePrices": true, "getBookingLinks": true,
		"findAvailableSlots": true,
	}
	if role == domain.GuestAccessRole {
		return guest
	}
	if role == domain.PatientAccessRole {
		for name := range map[string]bool{"verifyPatient": true, "createAppointment": true, "cancelAppointment": true} {
			guest[name] = true
		}
		return guest
	}
	if role == domain.DoctorAccessRole {
		for name := range map[string]bool{"listInfoCollections": true, "listInfoRecords": true, "getInfoRecord": true} {
			guest[name] = true
		}
		return guest
	}
	all := map[string]bool{}
	for _, name := range []string{"checkTime", "createPlan", "mockInfoHealth", "listInfoCollections", "listInfoRecords", "getInfoRecord", "createInfoRecord", "updateInfoRecord", "deleteInfoRecord", "searchInfo", "findAvailableSlots", "createAppointment", "cancelAppointment", "verifyPatient", "searchHospitalKnowledge", "getHospitalInfo", "getHospitalHours", "getEmergencyInfo", "listDoctors", "getDoctorSchedules", "listDepartments", "listMedicalServices", "getMedicalService", "getServicePrices", "getBookingLinks"} {
		all[name] = true
	}
	return all
}

func ensureToolAllowed(role domain.AccessRole, toolName string) error {
	if !roleToolNames(role)[toolName] {
		return fmt.Errorf("tool %q is not available for role %s", toolName, role)
	}
	return nil
}
