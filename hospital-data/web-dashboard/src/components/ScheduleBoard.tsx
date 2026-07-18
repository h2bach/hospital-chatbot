import { CalendarPlus, Clock3, GripVertical, MapPin, Pencil, Trash2, UserRound, UserRoundPlus } from "lucide-react"
import { useMemo, useState, type DragEvent } from "react"
import type { JsonObject, ReferenceData } from "../types"
import {
  buildManualAssignment,
  scheduleDayLabel,
  scheduleShiftOptions,
  scheduleWeekDates,
  shiftLabel,
  text,
} from "../lib/scheduling"

type DraggedItem =
  | { type: "doctor"; staffID: string }
  | { type: "assignment"; assignmentID: string }
  | null

type ScheduleBoardProps = {
  schedule: JsonObject
  records: JsonObject[]
  references: ReferenceData
  query: string
  onChange: (records: JsonObject[], message: string) => void
  onEdit: (record: JsonObject, index: number) => void
  onDelete: (index: number) => void
  onMessage: (kind: "error" | "info", message: string) => void
}

function doctorSubtitle(doctor: JsonObject) {
  return text(doctor.credential_normalized) || text(doctor.credential_raw) || text(doctor.staff_id)
}

export function ScheduleBoard({
  schedule,
  records,
  references,
  query,
  onChange,
  onEdit,
  onDelete,
  onMessage,
}: ScheduleBoardProps) {
  const [selectedDoctorID, setSelectedDoctorID] = useState("")
  const [defaultRoomID, setDefaultRoomID] = useState("")
  const [defaultShift, setDefaultShift] = useState("FULL_DAY")
  const [dragged, setDragged] = useState<DraggedItem>(null)
  const [dragOverDate, setDragOverDate] = useState("")
  const weekStart = text(schedule.week_start)
  const weekDates = scheduleWeekDates(weekStart)
  const normalizedQuery = query.trim().toLocaleLowerCase("vi")
  const doctors = useMemo(
    () => references.doctors.filter((doctor) => {
      if (!normalizedQuery) return true
      return `${text(doctor.full_name)} ${text(doctor.staff_id)} ${doctorSubtitle(doctor)}`
        .toLocaleLowerCase("vi")
        .includes(normalizedQuery)
    }),
    [normalizedQuery, references.doctors],
  )
  const doctorsByID = useMemo(
    () => new Map(references.doctors.map((doctor) => [text(doctor.staff_id), doctor])),
    [references.doctors],
  )
  const roomsByID = useMemo(
    () => new Map(references.rooms.map((room) => [text(room.room_id), room])),
    [references.rooms],
  )

  function slotIsOccupied(staffID: string, scheduleDate: string, shiftCode: string, ignoredID = "") {
    return records.some((record) => {
      if (text(record.assignment_id) === ignoredID) return false
      if (text(record.staff_id) !== staffID || text(record.schedule_date) !== scheduleDate) return false
      const currentShift = text(record.shift_code)
      return currentShift === shiftCode || currentShift === "FULL_DAY" || shiftCode === "FULL_DAY"
    })
  }

  function addDoctor(staffID: string, scheduleDate: string) {
    const doctor = doctorsByID.get(staffID)
    if (!doctor) return
    if (slotIsOccupied(staffID, scheduleDate, defaultShift)) {
      onMessage("error", `${text(doctor.full_name)} đã có phân công trùng ca trong ngày này.`)
      return
    }
    const assignment = buildManualAssignment(
      schedule,
      records,
      doctor,
      scheduleDate,
      defaultRoomID,
      defaultShift,
      references,
    )
    onChange([...records, assignment], `Đã xếp ${text(doctor.full_name)} vào ${scheduleDate}.`)
  }

  function moveAssignment(assignmentID: string, scheduleDate: string) {
    const index = records.findIndex((record) => text(record.assignment_id) === assignmentID)
    if (index < 0 || text(records[index].schedule_date) === scheduleDate) return
    const record = records[index]
    if (slotIsOccupied(text(record.staff_id), scheduleDate, text(record.shift_code), assignmentID)) {
      onMessage("error", `${text(record.staff_name)} đã có phân công trùng ca trong ngày đích.`)
      return
    }
    const next = [...records]
    next[index] = { ...record, schedule_date: scheduleDate, published_status: "DRAFT" }
    onChange(next, `Đã chuyển ${text(record.staff_name)} sang ${scheduleDate}.`)
  }

  function startDrag(event: DragEvent, item: Exclude<DraggedItem, null>) {
    setDragged(item)
    event.dataTransfer.effectAllowed = item.type === "doctor" ? "copy" : "move"
    event.dataTransfer.setData("text/plain", JSON.stringify(item))
  }

  function readDragged(event: DragEvent): Exclude<DraggedItem, null> | null {
    if (dragged) return dragged
    try {
      return JSON.parse(event.dataTransfer.getData("text/plain")) as Exclude<DraggedItem, null>
    } catch {
      return null
    }
  }

  function dropOnDay(event: DragEvent, scheduleDate: string) {
    event.preventDefault()
    const item = readDragged(event)
    if (item?.type === "doctor") addDoctor(item.staffID, scheduleDate)
    if (item?.type === "assignment") moveAssignment(item.assignmentID, scheduleDate)
    setDragged(null)
    setDragOverDate("")
  }

  return (
    <div className="schedule-board">
      <div className="board-controls">
        <div className="board-help">
          <span><GripVertical size={15} /> Kéo bác sĩ vào ngày</span>
          <small>Hoặc chọn bác sĩ, sau đó bấm dấu cộng ở cột ngày.</small>
        </div>
        <div className="assignment-defaults" aria-label="Thiết lập cho phân công mới">
          <label>
            Phòng mặc định
            <select value={defaultRoomID} onChange={(event) => setDefaultRoomID(event.target.value)}>
              <option value="">Chưa chọn phòng</option>
              {references.rooms.map((room) => (
                <option key={text(room.room_id)} value={text(room.room_id)}>
                  {text(room.display_name) || text(room.room_id)} · {text(room.room_id)} · {text(room.facility_id)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ca mặc định
            <select value={defaultShift} onChange={(event) => setDefaultShift(event.target.value)}>
              {scheduleShiftOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="weekly-planner">
        <aside className="doctor-pool" aria-label="Danh sách bác sĩ">
          <div className="pool-heading">
            <div><UserRound size={17} /><strong>Bác sĩ</strong></div>
            <span>{doctors.length}/{references.doctors.length}</span>
          </div>
          <p>Chọn hoặc kéo một bác sĩ sang lịch tuần.</p>
          <div className="doctor-list">
            {doctors.map((doctor) => {
              const staffID = text(doctor.staff_id)
              const selected = selectedDoctorID === staffID
              return (
                <article
                  className={`doctor-chip ${selected ? "selected" : ""}`}
                  data-staff-id={staffID}
                  draggable
                  key={staffID}
                  onDragStart={(event) => startDrag(event, { type: "doctor", staffID })}
                  onDragEnd={() => setDragged(null)}
                >
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedDoctorID(selected ? "" : staffID)}
                  >
                    <span className="doctor-avatar">{text(doctor.full_name).trim().slice(0, 1) || "BS"}</span>
                    <span><strong>{text(doctor.full_name)}</strong><small>{doctorSubtitle(doctor)} · {staffID}</small></span>
                  </button>
                  <GripVertical size={15} aria-hidden="true" />
                </article>
              )
            })}
            {!doctors.length && <div className="pool-empty">Không tìm thấy bác sĩ phù hợp.</div>}
          </div>
        </aside>

        <div className="week-columns" aria-label={`Lịch tuần bắt đầu ${weekStart}`}>
          {weekDates.map((scheduleDate, dayIndex) => {
            const day = scheduleDayLabel(scheduleDate, dayIndex)
            const assignments = records
              .map((record, index) => ({ record, index }))
              .filter(({ record }) => text(record.schedule_date) === scheduleDate)
              .sort((left, right) => text(left.record.start_time).localeCompare(text(right.record.start_time)) || text(left.record.staff_name).localeCompare(text(right.record.staff_name), "vi"))
            return (
              <section
                className={`day-column ${dragOverDate === scheduleDate ? "drag-over" : ""} ${dayIndex > 4 ? "weekend" : ""}`}
                data-schedule-date={scheduleDate}
                key={scheduleDate}
                onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = dragged?.type === "doctor" ? "copy" : "move"; setDragOverDate(scheduleDate) }}
                onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragOverDate("") }}
                onDrop={(event) => dropOnDay(event, scheduleDate)}
              >
                <header className="day-heading">
                  <div><strong>{day.weekday}</strong><span>{day.date}</span></div>
                  <span className="day-count">{assignments.length}</span>
                </header>
                <button
                  type="button"
                  className="quick-assign"
                  disabled={!selectedDoctorID}
                  onClick={() => selectedDoctorID && addDoctor(selectedDoctorID, scheduleDate)}
                  aria-label={`Thêm bác sĩ đã chọn vào ${day.weekday} ${day.date}`}
                >
                  <CalendarPlus size={15} /> {selectedDoctorID ? "Thêm bác sĩ đã chọn" : "Thả bác sĩ vào đây"}
                </button>
                <div className="day-assignments">
                  {assignments.map(({ record, index }) => {
                    const assignmentID = text(record.assignment_id)
                    const room = roomsByID.get(text(record.room_id))
                    return (
                      <article
                        className="assignment-card"
                        data-assignment-id={assignmentID}
                        draggable
                        key={assignmentID}
                        onDragStart={(event) => startDrag(event, { type: "assignment", assignmentID })}
                        onDragEnd={() => { setDragged(null); setDragOverDate("") }}
                      >
                        <div className="assignment-card-top">
                          <span className="assignment-avatar">{text(record.staff_name).trim().slice(0, 1) || "BS"}</span>
                          <div><strong>{text(record.staff_name) || text(record.staff_id)}</strong><small>{text(record.staff_id)}</small></div>
                          <GripVertical size={14} aria-hidden="true" />
                        </div>
                        <div className="assignment-meta">
                          <span><Clock3 size={13} /> {shiftLabel(record.shift_code)}</span>
                          <span className={!room ? "missing" : ""}><MapPin size={13} /> {room ? text(room.display_name) || text(room.room_id) : "Chưa chọn phòng"}</span>
                        </div>
                        <div className="assignment-actions">
                          <button type="button" onClick={() => onEdit(record, index)} aria-label={`Sửa phân công của ${text(record.staff_name)}`}><Pencil size={14} /> Sửa</button>
                          <button type="button" className="remove" onClick={() => onDelete(index)} aria-label={`Xóa phân công của ${text(record.staff_name)}`}><Trash2 size={14} /></button>
                        </div>
                      </article>
                    )
                  })}
                  {!assignments.length && (
                    <div className="day-empty"><UserRoundPlus size={19} /><span>Chưa có bác sĩ</span></div>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
