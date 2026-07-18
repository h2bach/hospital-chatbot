export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export type JsonObject = { [key: string]: JsonValue }

export type DatasetSummary = {
  name: string
  filename: string
  title: string
  description: string
  kind: "array" | "object"
  primary_key?: string
  record_path?: string
  preview_fields?: string[]
  count: number
  version: string
  updated_at: string
}

export type DatasetPayload = {
  dataset: DatasetSummary
  data: JsonValue
}

export type DatasetListPayload = {
  data: DatasetSummary[]
  revision: number
}

export type ChangeEvent = {
  type: "stream.ready" | "dataset.changed"
  datasets: string[]
  revision: number
  changed_at: string
}

export type ReferenceData = {
  doctors: JsonObject[]
  facilities: JsonObject[]
  rooms: JsonObject[]
  patterns: JsonObject[]
}
