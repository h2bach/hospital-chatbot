import type { JsonObject, JsonValue, ReferenceData } from "../types"

export const scheduleShiftOptions = [
  { value: "FULL_DAY", label: "Cả ngày" },
  { value: "AM", label: "Buổi sáng" },
  { value: "PM", label: "Buổi chiều" },
] as const

const patternDayIndexes: Record<string, number[]> = {
  "Thứ 2-Thứ 6": [0, 1, 2, 3, 4],
  "Thứ 2-Thứ 5": [0, 1, 2, 3],
  "Thứ 2/4/6": [0, 2, 4],
  "Thứ 3/5": [1, 3],
  "Thứ 3": [1],
  "Thứ 5": [3],
  "Thứ 6": [4],
  "Thứ 7": [5],
  "Chủ nhật": [6],
}

const patternShiftCodes: Record<string, string> = {
  "Cả ngày": "FULL_DAY",
  Sáng: "AM",
  Chiều: "PM",
}

export function text(value: JsonValue | undefined) {
  return value === null || value === undefined ? "" : String(value)
}

function parseISODate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  return Number.isNaN(date.getTime()) ? null : date
}

export function addDays(value: string, amount: number) {
  const date = parseISODate(value)
  if (!date) return value
  date.setUTCDate(date.getUTCDate() + amount)
  return date.toISOString().slice(0, 10)
}

export function isMonday(value: string) {
  return parseISODate(value)?.getUTCDay() === 1
}

export function scheduleWeekDates(weekStart: string) {
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index))
}

export function scheduleDayLabel(value: string, index: number) {
  const labels = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
  const date = parseISODate(value)
  return {
    weekday: labels[index],
    date: date
      ? new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(date)
      : value,
  }
}

function nextAssignmentID(weekStart: string, records: JsonObject[]) {
  const prefix = `ASG-${weekStart.replaceAll("-", "")}-`
  const maximum = records.reduce((current, record) => {
    const id = text(record.assignment_id)
    if (!id.startsWith(prefix)) return current
    const suffix = Number(id.slice(prefix.length))
    return Number.isFinite(suffix) ? Math.max(current, suffix) : current
  }, 0)
  return `${prefix}${String(maximum + 1).padStart(4, "0")}`
}

export function shiftLabel(value: JsonValue | undefined) {
  return scheduleShiftOptions.find((option) => option.value === value)?.label || text(value) || "Chưa chọn ca"
}

export function buildManualAssignment(
  schedule: JsonObject,
  records: JsonObject[],
  doctor: JsonObject,
  scheduleDate: string,
  roomID: string,
  shiftCode: string,
  references: ReferenceData,
): JsonObject {
  const weekStart = text(schedule.week_start) || scheduleDate
  const room = references.rooms.find((item) => text(item.room_id) === roomID)
  const hasRoom = Boolean(room)
  return {
    assignment_id: nextAssignmentID(weekStart, records),
    week_start: weekStart,
    schedule_date: scheduleDate,
    facility_id: room ? text(room.facility_id) : null,
    area_id: room ? text(room.area_id) : null,
    room_id: room ? text(room.room_id) : null,
    staff_id: text(doctor.staff_id),
    staff_name: text(doctor.full_name),
    shift_code: shiftCode,
    start_time: room && shiftCode === "FULL_DAY" ? text(room.opens_at) || null : null,
    end_time: room && shiftCode === "FULL_DAY" ? text(room.closes_at) || null : null,
    assignment_scope: hasRoom ? "ROOM" : "AREA",
    assignment_status: "WORKING",
    source_version: text(schedule.source_version) || `MANUAL_DASHBOARD_${weekStart}_v1`,
    source_image: null,
    note: hasRoom ? "Phân công thủ công trên dashboard." : "Chưa chọn phòng; cần hoàn thiện trước khi công bố.",
    published_status: "DRAFT",
  }
}

export function buildPatternSuggestions(references: ReferenceData, weekStart: string) {
  if (!isMonday(weekStart)) return []
  const rooms = new Map(references.rooms.map((room) => [text(room.room_id), room]))
  const doctors = new Map(references.doctors.map((doctor) => [text(doctor.staff_id), doctor]))
  const output: JsonObject[] = []
  let counter = 1

  for (const pattern of references.patterns) {
    const days = patternDayIndexes[text(pattern.applies_on)] || []
    const staffID = text(pattern.staff_id)
    const roomID = text(pattern.room_or_scope)
    const shiftCode = patternShiftCodes[text(pattern.shift)]
    const room = rooms.get(roomID)
    const doctor = doctors.get(staffID)
    if (!days.length || !staffID || !shiftCode || !room || !doctor) continue

    for (const dayIndex of days) {
      output.push({
        assignment_id: `ASG-${weekStart.replaceAll("-", "")}-${String(counter).padStart(4, "0")}`,
        week_start: weekStart,
        schedule_date: addDays(weekStart, dayIndex),
        facility_id: text(room.facility_id),
        area_id: text(room.area_id),
        room_id: roomID,
        staff_id: staffID,
        staff_name: text(doctor.full_name),
        shift_code: shiftCode,
        start_time: shiftCode === "FULL_DAY" ? text(room.opens_at) || null : null,
        end_time: shiftCode === "FULL_DAY" ? text(room.closes_at) || null : null,
        assignment_scope: "ROOM",
        assignment_status: "WORKING",
        source_version: `PATTERN_SUGGESTION_${weekStart}_v1`,
        source_image: null,
        note: `Gợi ý từ ${text(pattern.pattern_id)} (${text(pattern.confidence)}); phải xác minh trước khi công bố.`,
        published_status: "DRAFT",
      })
      counter += 1
    }
  }
  return output
}

function activeAssignment(record: JsonObject) {
  const status = text(record.assignment_status)
  return Boolean(text(record.staff_id)) && (status === "WORKING" || status === "AREA_DUTY")
}

function shiftsOverlap(left: JsonObject, right: JsonObject) {
  const leftShift = text(left.shift_code)
  const rightShift = text(right.shift_code)
  if (leftShift === rightShift) return true
  if (leftShift === "FULL_DAY" || rightShift === "FULL_DAY") return true
  const leftStart = text(left.start_time)
  const leftEnd = text(left.end_time)
  const rightStart = text(right.start_time)
  const rightEnd = text(right.end_time)
  return Boolean(leftStart && leftEnd && rightStart && rightEnd && leftStart < rightEnd && rightStart < leftEnd)
}

export function findScheduleConflict(records: JsonObject[]) {
  for (let index = 0; index < records.length; index += 1) {
    const current = records[index]
    if (!activeAssignment(current)) continue
    for (let otherIndex = 0; otherIndex < index; otherIndex += 1) {
      const other = records[otherIndex]
      if (
        activeAssignment(other) &&
        text(other.staff_id) === text(current.staff_id) &&
        text(other.schedule_date) === text(current.schedule_date) &&
        shiftsOverlap(other, current)
      ) {
        return { current, other }
      }
    }
  }
  return null
}

export function shiftScheduleWeek(schedule: JsonObject, records: JsonObject[], nextWeekStart: string) {
  const currentWeekStart = text(schedule.week_start)
  const nextRecords = records.map((record) => {
    const currentDate = text(record.schedule_date)
    const offset = scheduleWeekDates(currentWeekStart).indexOf(currentDate)
    return {
      ...record,
      week_start: nextWeekStart,
      schedule_date: addDays(nextWeekStart, offset >= 0 ? offset : 0),
      published_status: "DRAFT",
    }
  })
  return {
    ...schedule,
    week_start: nextWeekStart,
    week_end: addDays(nextWeekStart, 6),
    published_status: "DRAFT",
    source_version: `MANUAL_DASHBOARD_${nextWeekStart}_v1`,
    assignments: nextRecords,
  } satisfies JsonObject
}
