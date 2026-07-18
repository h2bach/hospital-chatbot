import * as Dialog from "@radix-ui/react-dialog"
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BookOpenText,
  Braces,
  Building2,
  CalendarClock,
  Check,
  ChevronRight,
  CircleGauge,
  Database,
  FileCheck2,
  HeartPulse,
  Hospital,
  LoaderCircle,
  Menu,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Stethoscope,
  Trash2,
  UsersRound,
  Wifi,
  WifiOff,
  X,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { ScheduleBoard } from "./components/ScheduleBoard"
import { ApiError, getDataset, listDatasets, openDatasetEvents, updateDataset } from "./lib/api"
import {
  addDays,
  buildPatternSuggestions,
  findScheduleConflict,
  isMonday,
  shiftScheduleWeek,
  text,
} from "./lib/scheduling"
import type {
  ChangeEvent,
  DatasetPayload,
  DatasetSummary,
  JsonObject,
  JsonValue,
  ReferenceData,
} from "./types"

type EditorState = { record: JsonObject; index: number; isNew: boolean }
type ToastState = { kind: "success" | "error" | "info"; message: string }

const emptyReferences: ReferenceData = { doctors: [], facilities: [], rooms: [], patterns: [] }

const fieldLabels: Record<string, string> = {
  assignment_id: "Mã phân công",
  week_start: "Bắt đầu tuần",
  week_end: "Kết thúc tuần",
  schedule_date: "Ngày làm việc",
  facility_id: "Cơ sở",
  area_id: "Mã khu khám",
  room_id: "Phòng khám",
  staff_id: "Bác sĩ",
  staff_name: "Tên bác sĩ",
  shift_code: "Ca làm việc",
  start_time: "Giờ bắt đầu",
  end_time: "Giờ kết thúc",
  assignment_scope: "Phạm vi",
  assignment_status: "Trạng thái phân công",
  source_version: "Phiên bản nguồn",
  source_image: "Ảnh nguồn",
  published_status: "Trạng thái công bố",
  full_name: "Họ và tên",
  credential_raw: "Học hàm/học vị gốc",
  credential_normalized: "Học hàm/học vị chuẩn hóa",
  notes: "Ghi chú",
  note: "Ghi chú",
  name: "Tên",
  address: "Địa chỉ",
  timezone: "Múi giờ",
  display_name: "Tên hiển thị",
  opens_at: "Giờ mở cửa",
  closes_at: "Giờ đóng cửa",
  primary_key: "Khóa chính",
}

const selectOptions: Record<string, Array<{ value: string; label: string }>> = {
  shift_code: [
    { value: "FULL_DAY", label: "Cả ngày" },
    { value: "AM", label: "Buổi sáng" },
    { value: "PM", label: "Buổi chiều" },
  ],
  assignment_scope: [
    { value: "ROOM", label: "Theo phòng" },
    { value: "AREA", label: "Theo khu" },
  ],
  assignment_status: [
    { value: "WORKING", label: "Làm việc" },
    { value: "AREA_DUTY", label: "Trực khu" },
    { value: "OFF", label: "Nghỉ" },
    { value: "PROCEDURE", label: "Làm thủ thuật" },
    { value: "UNASSIGNED", label: "Chưa phân công" },
  ],
  published_status: [
    { value: "DRAFT", label: "Bản nháp" },
    { value: "PUBLISHED", label: "Đã công bố" },
    { value: "EMPTY", label: "Chưa có lịch" },
  ],
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function asRecords(value: JsonValue | undefined): JsonObject[] {
  if (!Array.isArray(value)) return []
  return value.filter(isObject)
}

function recordsFor(payload: DatasetPayload | null): JsonObject[] {
  if (!payload) return []
  if (payload.dataset.record_path && isObject(payload.data)) {
    return asRecords(payload.data[payload.dataset.record_path])
  }
  if (Array.isArray(payload.data)) return asRecords(payload.data)
  return isObject(payload.data) ? [payload.data] : []
}

function withRecords(payload: DatasetPayload, records: JsonObject[]): JsonValue {
  if (payload.dataset.record_path && isObject(payload.data)) {
    return { ...payload.data, [payload.dataset.record_path]: records }
  }
  return payload.dataset.kind === "array" ? records : records[0] || {}
}

function displayValue(value: JsonValue | undefined) {
  if (value === null || value === undefined || value === "") return "—"
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ") || "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function emptyLike(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return []
  if (isObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, emptyLike(child)]))
  }
  if (typeof value === "boolean") return false
  if (typeof value === "number") return 0
  return value === null ? null : ""
}

function makeNewRecord(payload: DatasetPayload, records: JsonObject[]): JsonObject {
  const template = records[0]
    ? (emptyLike(records[0]) as JsonObject)
    : ({ [payload.dataset.primary_key || "id"]: "" } as JsonObject)
  if (payload.dataset.name === "schedule" && isObject(payload.data)) {
    const week = String(payload.data.week_start || new Date().toISOString().slice(0, 10))
    return {
      assignment_id: `ASG-${week.replaceAll("-", "")}-${String(records.length + 1).padStart(4, "0")}`,
      week_start: week,
      schedule_date: week,
      facility_id: "",
      area_id: "",
      room_id: "",
      staff_id: "",
      staff_name: "",
      shift_code: "FULL_DAY",
      start_time: "",
      end_time: "",
      assignment_scope: "ROOM",
      assignment_status: "WORKING",
      source_version: String(payload.data.source_version || "MANUAL_DASHBOARD_v1"),
      source_image: null,
      note: "",
      published_status: String(payload.data.published_status || "DRAFT"),
    }
  }
  return template
}

function fold(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll("đ", "d")
    .replaceAll("Đ", "D")
    .toLowerCase()
}

function formatUpdated(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Chưa rõ"
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date)
}

function datasetIcon(name: string) {
  const icons: Record<string, typeof Database> = {
    schedule: CalendarClock,
    doctors: Stethoscope,
    facilities: Hospital,
    rooms: Building2,
    organization: Network,
    rules: ShieldCheck,
    patterns: SlidersHorizontal,
    dictionary: BookOpenText,
    sources: FileCheck2,
    metadata: Database,
  }
  return icons[name] || Database
}

function humanizeField(field: string) {
  return fieldLabels[field] || field.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())
}

function optionsFor(field: string, references: ReferenceData) {
  if (field === "staff_id") {
    return references.doctors.map((doctor) => ({
      value: String(doctor.staff_id || ""),
      label: `${doctor.full_name || doctor.staff_id} · ${doctor.staff_id}`,
    }))
  }
  if (field === "facility_id") {
    return references.facilities.map((facility) => ({
      value: String(facility.facility_id || ""),
      label: String(facility.name || facility.facility_id),
    }))
  }
  if (field === "room_id") {
    return references.rooms.map((room) => ({
      value: String(room.room_id || ""),
      label: `${room.display_name || room.room_id} · ${room.facility_id}`,
    }))
  }
  return selectOptions[field]
}

function RecordEditor({
  state,
  dataset,
  references,
  onClose,
  onSave,
}: {
  state: EditorState | null
  dataset: DatasetSummary | undefined
  references: ReferenceData
  onClose: () => void
  onSave: (record: JsonObject) => void
}) {
  const [values, setValues] = useState<JsonObject>({})
  const [nestedDrafts, setNestedDrafts] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState("")

  useEffect(() => {
    if (!state) return
    setValues(structuredClone(state.record))
    setNestedDrafts(
      Object.fromEntries(
        Object.entries(state.record)
          .filter(([, value]) => typeof value === "object" && value !== null)
          .map(([key, value]) => [key, JSON.stringify(value, null, 2)]),
      ),
    )
    setFormError("")
  }, [state])

  function updateField(field: string, value: JsonValue) {
    setValues((current) => {
      const next = { ...current, [field]: value }
      if (dataset?.name === "schedule" && field === "staff_id") {
        const doctor = references.doctors.find((item) => item.staff_id === value)
        if (doctor) next.staff_name = doctor.full_name
      }
      if (dataset?.name === "schedule" && field === "room_id") {
        const room = references.rooms.find((item) => item.room_id === value)
        if (room) {
          next.facility_id = room.facility_id
          next.area_id = room.area_id
          if (next.shift_code === "FULL_DAY") {
            next.start_time = room.opens_at
            next.end_time = room.closes_at
          }
        }
      }
      return next
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const next = { ...values }
    try {
      for (const [field, raw] of Object.entries(nestedDrafts)) {
        next[field] = JSON.parse(raw) as JsonValue
      }
    } catch {
      setFormError("Một trường JSON lồng nhau chưa đúng cú pháp.")
      return
    }
    const primaryKey = dataset?.primary_key
    if (primaryKey && !String(next[primaryKey] ?? "").trim()) {
      setFormError(`Trường ${humanizeField(primaryKey)} là bắt buộc.`)
      return
    }
    onSave(next)
  }

  return (
    <Dialog.Root open={Boolean(state)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content editor-dialog" aria-describedby="record-editor-description">
          <div className="dialog-heading">
            <div>
              <span className="eyebrow">{dataset?.title}</span>
              <Dialog.Title>{state?.isNew ? "Thêm bản ghi mới" : "Chỉnh sửa bản ghi"}</Dialog.Title>
              <Dialog.Description id="record-editor-description">
                Thay đổi được kiểm tra trước khi cập nhật vào dữ liệu dùng bởi chatbot.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Đóng cửa sổ">
              <X size={19} />
            </Dialog.Close>
          </div>

          <form onSubmit={submit} className="record-form">
            <div className="form-grid">
              {Object.entries(values).map(([field, value]) => {
                const id = `field-${field}`
                const options = optionsFor(field, references)
                const nested = typeof value === "object" && value !== null
                const wide = nested || ["address", "notes", "note", "rule", "weekend_pattern"].includes(field)
                return (
                  <div className={`form-field ${wide ? "form-field-wide" : ""}`} key={field}>
                    <label htmlFor={id}>
                      {humanizeField(field)}
                      {field === dataset?.primary_key && <span className="required"> *</span>}
                    </label>
                    {nested ? (
                      <textarea
                        id={id}
                        value={nestedDrafts[field] ?? ""}
                        onChange={(event) =>
                          setNestedDrafts((current) => ({ ...current, [field]: event.target.value }))
                        }
                        rows={4}
                        spellCheck={false}
                      />
                    ) : options ? (
                      <select
                        id={id}
                        value={String(value ?? "")}
                        onChange={(event) => updateField(field, event.target.value)}
                      >
                        <option value="">Chọn giá trị</option>
                        {options.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    ) : typeof value === "boolean" ? (
                      <select
                        id={id}
                        value={String(value)}
                        onChange={(event) => updateField(field, event.target.value === "true")}
                      >
                        <option value="true">Có</option>
                        <option value="false">Không</option>
                      </select>
                    ) : (
                      <input
                        id={id}
                        type={field.includes("date") || field === "week_start" || field === "week_end" ? "date" : field.endsWith("_time") ? "time" : typeof value === "number" ? "number" : "text"}
                        value={value === null ? "" : String(value)}
                        onChange={(event) =>
                          updateField(field, typeof value === "number" ? Number(event.target.value) : event.target.value || (value === null ? null : ""))
                        }
                      />
                    )}
                  </div>
                )
              })}
            </div>
            {formError && (
              <div className="inline-alert error" role="alert">
                <AlertTriangle size={17} /> {formError}
              </div>
            )}
            <div className="dialog-actions">
              <Dialog.Close className="button secondary" type="button">Hủy</Dialog.Close>
              <button className="button primary" type="submit">
                <Save size={17} /> Lưu bản ghi
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function ConfirmDelete({
  record,
  primaryKey,
  onClose,
  onConfirm,
}: {
  record: JsonObject | null
  primaryKey?: string
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog.Root open={Boolean(record)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content confirm-dialog" aria-describedby="delete-description">
          <div className="danger-icon"><Trash2 size={23} /></div>
          <Dialog.Title>Xóa bản ghi này?</Dialog.Title>
          <Dialog.Description id="delete-description">
            {primaryKey && record ? `Bản ghi ${displayValue(record[primaryKey])} sẽ bị xóa khỏi dữ liệu đang phục vụ chatbot. ` : ""}
            Thao tác sẽ được áp dụng ngay sau khi kiểm tra liên kết dữ liệu.
          </Dialog.Description>
          <div className="dialog-actions">
            <Dialog.Close className="button secondary">Giữ lại</Dialog.Close>
            <button className="button danger" type="button" onClick={onConfirm}>
              <Trash2 size={17} /> Xóa bản ghi
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function App() {
  const [summaries, setSummaries] = useState<DatasetSummary[]>([])
  const [revision, setRevision] = useState(0)
  const [selected, setSelected] = useState("schedule")
  const [payload, setPayload] = useState<DatasetPayload | null>(null)
  const [references, setReferences] = useState<ReferenceData>(emptyReferences)
  const [query, setQuery] = useState("")
  const [mode, setMode] = useState<"records" | "json">("records")
  const [rawText, setRawText] = useState("")
  const [dirty, setDirty] = useState(false)
  const [remoteChanged, setRemoteChanged] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [syncStatus, setSyncStatus] = useState<"connecting" | "live" | "offline">("connecting")
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null)
  const [toast, setToast] = useState<ToastState | null>(null)
  const [navOpen, setNavOpen] = useState(false)
  const [autoScheduleOpen, setAutoScheduleOpen] = useState(false)

  const selectedRef = useRef(selected)
  const dirtyRef = useRef(dirty)
  selectedRef.current = selected
  dirtyRef.current = dirty

  const refreshSummaries = useCallback(async () => {
    const result = await listDatasets()
    setSummaries(result.data)
    setRevision(result.revision)
  }, [])

  const loadOne = useCallback(async (name: string, quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const result = await getDataset(name)
      setPayload(result)
      setRawText(JSON.stringify(result.data, null, 2))
      setDirty(false)
      setRemoteChanged(false)
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Không tải được dữ liệu." })
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  const refreshReferences = useCallback(async () => {
    const [doctors, facilities, rooms, patterns] = await Promise.all([
      getDataset("doctors"),
      getDataset("facilities"),
      getDataset("rooms"),
      getDataset("patterns"),
    ])
    setReferences({
      doctors: asRecords(doctors.data),
      facilities: asRecords(facilities.data),
      rooms: asRecords(rooms.data),
      patterns: asRecords(patterns.data),
    })
  }, [])

  useEffect(() => {
    void refreshSummaries().catch((error: unknown) => {
      setLoading(false)
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Không kết nối được API." })
    })
  }, [refreshSummaries])

  useEffect(() => {
    setQuery("")
    setMode("records")
    setNavOpen(false)
    void loadOne(selected)
  }, [loadOne, selected])

  useEffect(() => {
    if (selected !== "schedule") return
    void refreshReferences().catch(() => setReferences(emptyReferences))
  }, [refreshReferences, selected])

  useEffect(() => {
    const events = openDatasetEvents()
    events.onopen = () => setSyncStatus("live")
    events.onerror = () => setSyncStatus("offline")
    const ready = (raw: Event) => {
      const event = JSON.parse((raw as MessageEvent<string>).data) as ChangeEvent
      setRevision(event.revision)
      setSyncStatus("live")
    }
    const changed = (raw: Event) => {
      const event = JSON.parse((raw as MessageEvent<string>).data) as ChangeEvent
      setRevision(event.revision)
      void refreshSummaries()
      if (
        selectedRef.current === "schedule" &&
        event.datasets.some((name) => name === "doctors" || name === "facilities" || name === "rooms" || name === "patterns")
      ) {
        void refreshReferences()
      }
      if (!event.datasets.includes(selectedRef.current)) return
      if (dirtyRef.current) {
        setRemoteChanged(true)
        setToast({ kind: "info", message: "Dữ liệu nguồn vừa thay đổi. Tải lại trước khi tiếp tục để tránh ghi đè." })
        return
      }
      void loadOne(selectedRef.current, true)
      setToast({ kind: "info", message: "Dashboard vừa nhận một cập nhật dữ liệu theo thời gian thực." })
    }
    events.addEventListener("stream.ready", ready)
    events.addEventListener("dataset.changed", changed)
    return () => {
      events.removeEventListener("stream.ready", ready)
      events.removeEventListener("dataset.changed", changed)
      events.close()
    }
  }, [loadOne, refreshReferences, refreshSummaries])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 5200)
    return () => window.clearTimeout(timeout)
  }, [toast])

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return
      event.preventDefault()
    }
    window.addEventListener("beforeunload", beforeUnload)
    return () => window.removeEventListener("beforeunload", beforeUnload)
  }, [])

  const records = useMemo(() => recordsFor(payload), [payload])
  const autoSuggestions = useMemo(() => {
    if (payload?.dataset.name !== "schedule" || !isObject(payload.data)) return []
    return buildPatternSuggestions(references, text(payload.data.week_start))
  }, [payload, references])
  const filteredRecords = useMemo(() => {
    const needle = fold(query.trim())
    if (!needle) return records.map((record, index) => ({ record, index }))
    return records
      .map((record, index) => ({ record, index }))
      .filter(({ record }) => fold(JSON.stringify(record)).includes(needle))
  }, [query, records])

  const columns = useMemo(() => {
    if (!payload) return []
    return Array.from(new Set([payload.dataset.primary_key, ...(payload.dataset.preview_fields || [])].filter(Boolean))) as string[]
  }, [payload])

  async function persist(nextData: JsonValue, successMessage: string) {
    if (!payload || saving) return
    setSaving(true)
    try {
      const result = await updateDataset(payload.dataset.name, payload.dataset.version, nextData)
      setPayload(result)
      setRawText(JSON.stringify(result.data, null, 2))
      setDirty(false)
      setRemoteChanged(false)
      setEditor(null)
      setDeleteIndex(null)
      setToast({ kind: "success", message: successMessage })
      await refreshSummaries()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setRemoteChanged(true)
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Không thể lưu dữ liệu." })
    } finally {
      setSaving(false)
    }
  }

  function selectDataset(name: string) {
    if (name === selected) return
    if (dirty) {
      setToast({ kind: "info", message: "Hãy lưu hoặc tải lại thay đổi hiện tại trước khi chuyển mục." })
      return
    }
    setSelected(name)
  }

  function updateScheduleMeta(field: string, value: JsonValue) {
    if (!payload || !isObject(payload.data)) return
    const nextData = { ...payload.data, [field]: value }
    setPayload({ ...payload, data: nextData })
    setRawText(JSON.stringify(nextData, null, 2))
    setDirty(true)
  }

  function updateScheduleWeek(nextWeekStart: string) {
    if (!payload || !isObject(payload.data) || !nextWeekStart) return
    if (!isMonday(nextWeekStart)) {
      setToast({ kind: "error", message: "Ngày bắt đầu tuần phải là Thứ Hai." })
      return
    }
    const nextData = shiftScheduleWeek(payload.data, records, nextWeekStart)
    setPayload({ ...payload, data: nextData })
    setRawText(JSON.stringify(nextData, null, 2))
    setDirty(true)
    setToast({ kind: "info", message: "Đã chuyển toàn bộ phân công sang tuần mới và đưa lịch về bản nháp." })
  }

  function stageScheduleRecords(nextRecords: JsonObject[], message: string) {
    if (!payload || payload.dataset.name !== "schedule") return
    const staged = withRecords(payload, nextRecords)
    const nextData = isObject(staged) ? { ...staged, published_status: "DRAFT" } : staged
    setPayload({ ...payload, data: nextData })
    setRawText(JSON.stringify(nextData, null, 2))
    setDirty(true)
    setToast({ kind: "info", message: `${message} Lịch đã được chuyển về bản nháp.` })
  }

  function scheduleDataForSave() {
    if (!payload || !isObject(payload.data)) return null
    const publishedStatus = text(payload.data.published_status) || "DRAFT"
    const weekStart = text(payload.data.week_start)
    const sourceVersion = text(payload.data.source_version) || `MANUAL_DASHBOARD_${weekStart}_v1`
    return {
      ...payload.data,
      imported_at: new Date().toISOString(),
      assignments: records.map((record) => ({
        ...record,
        week_start: weekStart,
        published_status: publishedStatus,
        source_version: sourceVersion,
      })),
    } satisfies JsonObject
  }

  function saveSchedule() {
    const nextData = scheduleDataForSave()
    if (!nextData) return
    const nextRecords = asRecords(nextData.assignments)
    const conflict = findScheduleConflict(nextRecords)
    if (conflict) {
      setToast({
        kind: "error",
        message: `${text(conflict.current.staff_name)} đang bị phân công trùng ca ngày ${text(conflict.current.schedule_date)}.`,
      })
      return
    }
    void persist(nextData, "Đã lưu lịch tuần và đồng bộ ngay tới chatbot.")
  }

  function applyAutomaticSchedule() {
    if (!payload || !isObject(payload.data)) return
    if (!autoSuggestions.length) {
      setToast({ kind: "error", message: "Không có mẫu nào đủ thông tin bác sĩ, phòng, ngày và ca để tự động phân công." })
      return
    }
    const weekStart = text(payload.data.week_start)
    const nextData: JsonObject = {
      ...payload.data,
      schema_version: text(payload.data.schema_version) || "1.0",
      week_start: weekStart,
      week_end: addDays(weekStart, 6),
      published_status: "DRAFT",
      source_version: `PATTERN_SUGGESTION_${weekStart}_v1`,
      imported_at: new Date().toISOString(),
      assignments: autoSuggestions,
    }
    setPayload({ ...payload, data: nextData })
    setRawText(JSON.stringify(nextData, null, 2))
    setDirty(true)
    setAutoScheduleOpen(false)
    setToast({ kind: "info", message: `Đã tạo ${autoSuggestions.length} phân công nháp từ mẫu quan sát. Hãy rà soát trước khi lưu.` })
  }

  function saveEditor(record: JsonObject) {
    if (!payload || !editor) return
    if (payload.dataset.kind === "object" && !payload.dataset.record_path) {
      void persist(record, "Đã cập nhật thông tin bộ dữ liệu.")
      return
    }
    const nextRecords = [...records]
    if (editor.isNew) nextRecords.push(record)
    else nextRecords[editor.index] = record
    if (payload.dataset.name === "schedule") {
      setEditor(null)
      stageScheduleRecords(nextRecords, editor.isNew ? "Đã thêm phân công vào bản nháp." : "Đã cập nhật phân công trong bản nháp.")
      return
    }
    void persist(withRecords(payload, nextRecords), editor.isNew ? "Đã thêm bản ghi mới." : "Đã cập nhật bản ghi.")
  }

  function confirmDelete() {
    if (!payload || deleteIndex === null) return
    const nextRecords = records.filter((_, index) => index !== deleteIndex)
    if (payload.dataset.name === "schedule") {
      setDeleteIndex(null)
      stageScheduleRecords(nextRecords, "Đã bỏ phân công khỏi bản nháp.")
      return
    }
    void persist(withRecords(payload, nextRecords), "Đã xóa bản ghi khỏi dữ liệu.")
  }

  function saveRawJSON() {
    try {
      const parsed = JSON.parse(rawText) as JsonValue
      void persist(parsed, "Đã lưu toàn bộ JSON và đồng bộ tới chatbot.")
    } catch {
      setToast({ kind: "error", message: "JSON chưa đúng cú pháp. Vui lòng kiểm tra dấu phẩy và dấu ngoặc." })
    }
  }

  function switchMode(nextMode: "records" | "json") {
    if (mode === nextMode) return
    if (dirty) {
      setToast({ kind: "info", message: "Hãy lưu hoặc tải lại thay đổi trước khi đổi chế độ hiển thị." })
      return
    }
    setMode(nextMode)
  }

  const currentSummary = summaries.find((item) => item.name === selected) || payload?.dataset
  const deleteRecord = deleteIndex === null ? null : records[deleteIndex]

  return (
    <>
      <a href="#main-content" className="skip-link">Bỏ qua điều hướng</a>
      <div className="app-shell">
        <aside className={`sidebar ${navOpen ? "sidebar-open" : ""}`} aria-label="Danh mục dữ liệu">
          <div className="brand">
            <div className="brand-mark"><HeartPulse size={23} /></div>
            <div>
              <strong>Tim Hà Nội</strong>
              <span>Data Operations</span>
            </div>
            <button className="icon-button sidebar-close" onClick={() => setNavOpen(false)} aria-label="Đóng menu">
              <X size={19} />
            </button>
          </div>

          <div className="workspace-label">Không gian quản trị</div>
          <nav className="dataset-nav">
            {summaries.map((item) => {
              const Icon = datasetIcon(item.name)
              return (
                <button
                  key={item.name}
                  className={selected === item.name ? "active" : ""}
                  onClick={() => selectDataset(item.name)}
                  aria-current={selected === item.name ? "page" : undefined}
                >
                  <span className="nav-icon"><Icon size={18} /></span>
                  <span className="nav-copy"><strong>{item.title}</strong><small>{item.count} bản ghi</small></span>
                  <ChevronRight className="nav-chevron" size={16} />
                </button>
              )
            })}
          </nav>

          <div className="sidebar-footer">
            <div className={`live-indicator ${syncStatus}`}>
              {syncStatus === "live" ? <Wifi size={16} /> : syncStatus === "offline" ? <WifiOff size={16} /> : <LoaderCircle className="spin" size={16} />}
              <div><strong>{syncStatus === "live" ? "Đồng bộ trực tiếp" : syncStatus === "offline" ? "Đang kết nối lại" : "Đang kết nối"}</strong><span>Revision #{revision || "—"}</span></div>
            </div>
          </div>
        </aside>
        {navOpen && <button className="nav-scrim" onClick={() => setNavOpen(false)} aria-label="Đóng menu" />}

        <main id="main-content" className="main-panel">
          <header className="topbar">
            <button className="icon-button menu-button" onClick={() => setNavOpen(true)} aria-label="Mở menu dữ liệu"><Menu size={20} /></button>
            <div className="breadcrumb"><Database size={16} /><span>Hospital data</span><ChevronRight size={14} /><strong>{currentSummary?.title || "Đang tải"}</strong></div>
            <div className="topbar-actions">
              <span className={`sync-pill ${syncStatus}`}><span className="status-dot" />{syncStatus === "live" ? "Live" : "Offline"}</span>
              <a className="chat-link" href="http://localhost:8080" target="_blank" rel="noreferrer">Mở chatbot <ArrowUpRight size={16} /></a>
            </div>
          </header>

          <div className="content-wrap">
            <section className="page-heading">
              <div>
                <div className="heading-kicker"><CircleGauge size={16} /> Trung tâm điều hành dữ liệu</div>
                <h1>{currentSummary?.title || "Đang tải dữ liệu"}</h1>
                <p>{currentSummary?.description || "Toàn bộ thay đổi được đồng bộ ngay tới dịch vụ thông tin bệnh viện."}</p>
              </div>
              <div className="heading-actions">
                <button className="button secondary" onClick={() => void loadOne(selected)} disabled={loading || saving}>
                  <RefreshCw className={loading ? "spin" : ""} size={17} /> Tải lại
                </button>
                {payload && (payload.dataset.kind === "array" || payload.dataset.record_path) && mode === "records" && (
                  <button className="button primary" onClick={() => setEditor({ record: makeNewRecord(payload, records), index: records.length, isNew: true })}>
                    <Plus size={18} /> {payload.dataset.name === "schedule" ? "Thêm phân công" : "Thêm bản ghi"}
                  </button>
                )}
              </div>
            </section>

            <section className="metrics-grid" aria-label="Tóm tắt dữ liệu">
              <article className="metric-card"><div className="metric-icon blue"><Database size={19} /></div><div><span>Tổng bản ghi</span><strong>{currentSummary?.count ?? "—"}</strong></div></article>
              <article className="metric-card"><div className="metric-icon green"><Activity size={19} /></div><div><span>Trạng thái API</span><strong>{syncStatus === "live" ? "Sẵn sàng" : "Kết nối lại"}</strong></div></article>
              <article className="metric-card"><div className="metric-icon amber"><Braces size={19} /></div><div><span>Phiên bản</span><strong className="metric-version">{currentSummary?.version || "—"}</strong></div></article>
              <article className="metric-card"><div className="metric-icon violet"><CalendarClock size={19} /></div><div><span>Cập nhật lúc</span><strong className="metric-date">{currentSummary ? formatUpdated(currentSummary.updated_at) : "—"}</strong></div></article>
            </section>

            {remoteChanged && (
              <div className="inline-alert warning" role="alert">
                <AlertTriangle size={18} />
                <span>Dữ liệu trên máy chủ mới hơn bản đang mở.</span>
                <button onClick={() => void loadOne(selected)}>Tải bản mới</button>
              </div>
            )}

            {payload?.dataset.name === "schedule" && isObject(payload.data) && mode === "records" && (
              <section className="schedule-card">
                <div className="section-heading">
                  <div><span className="eyebrow">Thiết lập tuần hiện hành</span><h2>Thông tin công bố lịch</h2></div>
                  <div className="schedule-heading-actions">
                    {dirty && <span className="unsaved-badge">Chưa lưu</span>}
                    <button className="button auto-button" type="button" onClick={() => setAutoScheduleOpen(true)} disabled={!autoSuggestions.length || saving || remoteChanged}>
                      <Sparkles size={16} /> Tự động phân công
                    </button>
                  </div>
                </div>
                <div className="schedule-fields">
                  <label>Thứ Hai bắt đầu tuần<input type="date" value={String(payload.data.week_start || "")} onChange={(event) => updateScheduleWeek(event.target.value)} /></label>
                  <label>Chủ Nhật kết thúc tuần<input type="date" value={String(payload.data.week_end || "")} readOnly aria-readonly="true" /></label>
                  <label>Trạng thái<select value={String(payload.data.published_status || "DRAFT")} onChange={(event) => updateScheduleMeta("published_status", event.target.value)}>{selectOptions.published_status.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                  <label>Phiên bản nguồn<input value={String(payload.data.source_version || "")} onChange={(event) => updateScheduleMeta("source_version", event.target.value || null)} /></label>
                  <button className="button primary schedule-save" disabled={!dirty || saving || remoteChanged} onClick={saveSchedule}><Save size={17} /> Lưu lịch</button>
                </div>
              </section>
            )}

            <section className="data-card">
              <div className="data-toolbar">
                <div className="search-box"><Search size={18} /><label htmlFor="dataset-search" className="sr-only">Tìm trong dữ liệu</label><input id="dataset-search" placeholder={payload?.dataset.name === "schedule" ? "Tìm bác sĩ để phân công…" : "Tìm theo mã, tên hoặc nội dung…"} value={query} onChange={(event) => setQuery(event.target.value)} disabled={mode === "json"} />{query && <button onClick={() => setQuery("")} aria-label="Xóa tìm kiếm"><X size={16} /></button>}</div>
                <div className="toolbar-right">
                  {mode === "records" && <span className="result-count">{payload?.dataset.name === "schedule" ? `${records.length} phân công` : `${filteredRecords.length} kết quả`}</span>}
                  <div className="view-switch" aria-label="Chế độ hiển thị">
                    <button className={mode === "records" ? "active" : ""} onClick={() => switchMode("records")}>{payload?.dataset.name === "schedule" ? <CalendarClock size={16} /> : <UsersRound size={16} />} {payload?.dataset.name === "schedule" ? "Lịch tuần" : "Dữ liệu"}</button>
                    <button className={mode === "json" ? "active" : ""} onClick={() => switchMode("json")}><Braces size={16} /> JSON</button>
                  </div>
                </div>
              </div>

              {loading ? (
                <div className="loading-state"><LoaderCircle className="spin" size={28} /><strong>Đang tải dữ liệu…</strong><span>Đọc snapshot mới nhất từ hospital-info-service</span></div>
              ) : mode === "json" ? (
                <div className="json-editor-wrap">
                  <div className="json-notice"><Braces size={18} /><div><strong>Chế độ toàn quyền</strong><span>Có thể thay đổi mọi trường và cấu trúc JSON. API sẽ kiểm tra kiểu dữ liệu, khóa chính và liên kết trước khi ghi.</span></div></div>
                  <label htmlFor="raw-json" className="sr-only">Nội dung JSON của bộ dữ liệu</label>
                  <textarea id="raw-json" className="json-editor" value={rawText} onChange={(event) => { setRawText(event.target.value); setDirty(true) }} spellCheck={false} />
                  <div className="json-actions"><span>{dirty ? "Có thay đổi chưa lưu" : "JSON khớp với dữ liệu trên máy chủ"}</span><button className="button primary" disabled={!dirty || saving || remoteChanged} onClick={saveRawJSON}>{saving ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} Lưu toàn bộ JSON</button></div>
                </div>
              ) : payload?.dataset.kind === "object" && !payload.dataset.record_path ? (
                <div className="object-view">
                  <div className="object-grid">
                    {isObject(payload.data) && Object.entries(payload.data).map(([field, value]) => (
                      <article key={field}><span>{humanizeField(field)}</span><strong>{displayValue(value)}</strong></article>
                    ))}
                  </div>
                  <button className="button primary" onClick={() => isObject(payload.data) && setEditor({ record: payload.data, index: 0, isNew: false })}><Pencil size={17} /> Sửa thông tin</button>
                </div>
              ) : payload?.dataset.name === "schedule" && isObject(payload.data) ? (
                <ScheduleBoard
                  schedule={payload.data}
                  records={records}
                  references={references}
                  query={query}
                  onChange={stageScheduleRecords}
                  onEdit={(record, index) => setEditor({ record, index, isNew: false })}
                  onDelete={setDeleteIndex}
                  onMessage={(kind, message) => setToast({ kind, message })}
                />
              ) : filteredRecords.length === 0 ? (
                <div className="empty-state"><div><Search size={24} /></div><strong>Không có bản ghi phù hợp</strong><span>Thử từ khóa khác hoặc thêm một bản ghi mới.</span></div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead><tr>{columns.map((column) => <th key={column}>{humanizeField(column)}</th>)}<th className="actions-column"><span className="sr-only">Thao tác</span></th></tr></thead>
                    <tbody>
                      {filteredRecords.map(({ record, index }) => (
                        <tr key={`${displayValue(record[payload?.dataset.primary_key || "id"])}-${index}`}>
                          {columns.map((column, columnIndex) => <td key={column} className={columnIndex === 0 ? "primary-cell" : ""}><span className="mobile-label">{humanizeField(column)}</span>{column === "assignment_status" || column === "published_status" ? <span className={`status-badge ${String(record[column] || "").toLowerCase()}`}>{displayValue(record[column])}</span> : displayValue(record[column])}</td>)}
                          <td className="row-actions"><button className="icon-button" onClick={() => setEditor({ record, index, isNew: false })} aria-label={`Sửa ${displayValue(record[payload?.dataset.primary_key || "id"])}`}><Pencil size={16} /></button><button className="icon-button danger-ghost" onClick={() => setDeleteIndex(index)} aria-label={`Xóa ${displayValue(record[payload?.dataset.primary_key || "id"])}`}><Trash2 size={16} /></button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <footer className="page-footer"><ShieldCheck size={16} /> Ghi nguyên tử · Kiểm tra phiên bản · Đồng bộ SSE · Tự nạp thay đổi bên ngoài</footer>
          </div>
        </main>
      </div>

      <RecordEditor state={editor} dataset={payload?.dataset} references={references} onClose={() => setEditor(null)} onSave={saveEditor} />
      <ConfirmDelete record={deleteRecord} primaryKey={payload?.dataset.primary_key} onClose={() => setDeleteIndex(null)} onConfirm={confirmDelete} />
      <Dialog.Root open={autoScheduleOpen} onOpenChange={setAutoScheduleOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content confirm-dialog auto-dialog" aria-describedby="auto-schedule-description">
            <div className="auto-icon"><Sparkles size={23} /></div>
            <Dialog.Title>Tự động phân công tuần này?</Dialog.Title>
            <Dialog.Description id="auto-schedule-description">
              Hệ thống sẽ thay bản nháp đang mở bằng các phân công ánh xạ chắc chắn từ mẫu quan sát, giống chế độ <code>--suggest-from-patterns</code> của script. Kết quả chưa được công bố cho tới khi bạn rà soát và lưu.
            </Dialog.Description>
            <div className="auto-summary"><strong>{autoSuggestions.length}</strong><span>phân công nháp sẽ được tạo</span></div>
            <div className="dialog-actions">
              <Dialog.Close className="button secondary" type="button">Hủy</Dialog.Close>
              <button className="button primary" type="button" onClick={applyAutomaticSchedule} disabled={!autoSuggestions.length}>
                <Sparkles size={17} /> Tạo lịch nháp
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="toast-region" aria-live="polite" aria-atomic="true">
        {toast && <div className={`toast ${toast.kind}`}>{toast.kind === "success" ? <Check size={18} /> : toast.kind === "error" ? <AlertTriangle size={18} /> : <Activity size={18} />}<span>{toast.message}</span><button onClick={() => setToast(null)} aria-label="Đóng thông báo"><X size={16} /></button></div>}
      </div>
      {saving && <div className="saving-bar" aria-live="polite"><LoaderCircle className="spin" size={15} /> Đang kiểm tra và đồng bộ dữ liệu…</div>}
    </>
  )
}
