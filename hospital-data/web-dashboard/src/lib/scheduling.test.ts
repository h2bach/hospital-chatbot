import { describe, expect, it } from "vitest"
import doctorsData from "../../../doctors.json"
import facilitiesData from "../../../facilities.json"
import patternsData from "../../../assignment_patterns.json"
import roomsData from "../../../rooms.json"
import type { JsonObject, ReferenceData } from "../types"
import {
  buildManualAssignment,
  buildPatternSuggestions,
  findScheduleConflict,
  shiftScheduleWeek,
} from "./scheduling"

const references: ReferenceData = {
  doctors: doctorsData as unknown as JsonObject[],
  facilities: facilitiesData as unknown as JsonObject[],
  rooms: roomsData as unknown as JsonObject[],
  patterns: patternsData as unknown as JsonObject[],
}

describe("weekly scheduling", () => {
  it("creates the same 70 safe suggestions as schedule_manager.py", () => {
    const suggestions = buildPatternSuggestions(references, "2026-07-20")

    expect(suggestions).toHaveLength(70)
    expect(suggestions[0]).toMatchObject({
      assignment_id: "ASG-20260720-0001",
      schedule_date: "2026-07-20",
      room_id: "306",
      staff_id: "NV045",
      published_status: "DRAFT",
    })
    expect(suggestions.every((record) => record.published_status === "DRAFT")).toBe(true)
    expect(suggestions.some((record) => record.schedule_date === "2026-07-25")).toBe(false)
    expect(suggestions.some((record) => record.schedule_date === "2026-07-26")).toBe(false)
  })

  it("builds a manual drag-and-drop assignment with the selected room", () => {
    const schedule = { week_start: "2026-07-20", source_version: "MANUAL_TEST_v1" }
    const assignment = buildManualAssignment(
      schedule,
      [],
      references.doctors[0],
      "2026-07-20",
      "TN1-PK01",
      "FULL_DAY",
      references,
    )

    expect(assignment).toMatchObject({
      assignment_id: "ASG-20260720-0001",
      schedule_date: "2026-07-20",
      facility_id: "CS1",
      area_id: "CS1_TN1",
      room_id: "TN1-PK01",
      staff_id: "NV001",
      assignment_status: "WORKING",
      published_status: "DRAFT",
    })
  })

  it("moves all assignments with the week and detects overlapping shifts", () => {
    const records = [
      { staff_id: "NV001", staff_name: "Bác sĩ A", schedule_date: "2026-07-13", shift_code: "FULL_DAY", assignment_status: "WORKING" },
      { staff_id: "NV001", staff_name: "Bác sĩ A", schedule_date: "2026-07-13", shift_code: "AM", assignment_status: "WORKING" },
    ] as JsonObject[]
    const moved = shiftScheduleWeek(
      { week_start: "2026-07-13", week_end: "2026-07-19", assignments: records },
      records,
      "2026-07-20",
    )

    expect((moved.assignments as JsonObject[])[0].schedule_date).toBe("2026-07-20")
    expect(moved.published_status).toBe("DRAFT")
    expect(findScheduleConflict(records)).not.toBeNull()
  })
})
