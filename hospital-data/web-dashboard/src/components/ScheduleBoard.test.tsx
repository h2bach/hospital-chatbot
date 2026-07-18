// @vitest-environment jsdom

import { fireEvent, render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { JsonObject, ReferenceData } from "../types"
import { ScheduleBoard } from "./ScheduleBoard"

const doctor: JsonObject = {
  staff_id: "NV001",
  full_name: "Bác sĩ Kiểm thử",
  credential_normalized: "BS",
}

const room: JsonObject = {
  room_id: "P01",
  display_name: "Phòng 01",
  facility_id: "CS1",
  area_id: "A01",
  opens_at: "07:30",
  closes_at: "16:30",
}

const references: ReferenceData = {
  doctors: [doctor],
  facilities: [],
  rooms: [room],
  patterns: [],
}

describe("ScheduleBoard", () => {
  it("adds a doctor when dragged into a day column", () => {
    const onChange = vi.fn()
    const { container } = render(
      <ScheduleBoard
        schedule={{ week_start: "2026-07-20", week_end: "2026-07-26", source_version: "TEST_v1" }}
        records={[]}
        references={references}
        query=""
        onChange={onChange}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onMessage={vi.fn()}
      />,
    )
    const doctorCard = container.querySelector<HTMLElement>('[data-staff-id="NV001"]')
    const monday = container.querySelector<HTMLElement>('[data-schedule-date="2026-07-20"]')
    expect(doctorCard).not.toBeNull()
    expect(monday).not.toBeNull()

    const dataTransfer = {
      effectAllowed: "copy",
      dropEffect: "copy",
      setData: vi.fn(),
      getData: vi.fn(() => JSON.stringify({ type: "doctor", staffID: "NV001" })),
    }
    fireEvent.dragStart(doctorCard!, { dataTransfer })
    fireEvent.dragOver(monday!, { dataTransfer })
    fireEvent.drop(monday!, { dataTransfer })

    expect(onChange).toHaveBeenCalledTimes(1)
    const nextRecords = onChange.mock.calls[0][0] as JsonObject[]
    expect(nextRecords[0]).toMatchObject({
      staff_id: "NV001",
      schedule_date: "2026-07-20",
      shift_code: "FULL_DAY",
      published_status: "DRAFT",
    })
  })
})
