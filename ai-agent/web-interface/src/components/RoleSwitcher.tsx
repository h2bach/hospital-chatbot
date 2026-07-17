import { ChevronDown, ShieldCheck } from "lucide-react"
import type { AccessRole } from "../types"

interface RoleSwitcherProps {
  value: AccessRole
  disabled?: boolean
  onChange: (role: AccessRole) => void
}

const roleDescriptions: Record<AccessRole, string> = {
  GUEST: "Tra cứu thông tin bệnh viện, lịch bác sĩ, dịch vụ, giá và kênh đặt lịch.",
  PATIENT: "Quyền khách và các thao tác lịch hẹn dành cho người bệnh đã xác minh.",
  DOCTOR: "Tra cứu thông tin chung và đọc dữ liệu chuyên môn được cấp quyền.",
  ADMIN: "Toàn bộ công cụ quản trị; chỉ dùng trong môi trường đã được ủy quyền.",
}

const roles: AccessRole[] = ["GUEST", "PATIENT", "DOCTOR", "ADMIN"]

export function RoleSwitcher({ value, disabled, onChange }: RoleSwitcherProps) {
  return (
    <label
      className="role-switcher"
      data-role={value}
      title={`ROLE ${value}: ${roleDescriptions[value]}`}
    >
      <ShieldCheck aria-hidden="true" />
      <span className="role-switcher-copy">
        <small>ROLE</small>
        <select
          value={value}
          disabled={disabled}
          aria-label="Chọn vai trò truy cập API"
          aria-describedby="role-switcher-description"
          onChange={(event) => onChange(event.target.value as AccessRole)}
        >
          {roles.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </span>
      <ChevronDown className="role-switcher-chevron" aria-hidden="true" />
      <span id="role-switcher-description" className="sr-only">
        {roleDescriptions[value]}
      </span>
    </label>
  )
}
