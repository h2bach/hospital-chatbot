import type { DatasetListPayload, DatasetPayload, JsonValue } from "../types"

type ErrorBody = { error?: { code?: string; message?: string } }

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  const body = (await response.json().catch(() => ({}))) as T & ErrorBody
  if (!response.ok) {
    throw new ApiError(
      body.error?.message || `Yêu cầu thất bại (${response.status})`,
      response.status,
      body.error?.code,
    )
  }
  return body
}

export function listDatasets() {
  return request<DatasetListPayload>("/api/v1/admin/datasets")
}

export function getDataset(name: string) {
  return request<DatasetPayload>(`/api/v1/admin/datasets/${encodeURIComponent(name)}`)
}

export function updateDataset(name: string, version: string, data: JsonValue) {
  return request<DatasetPayload>(`/api/v1/admin/datasets/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ version, data }),
  })
}

export function openDatasetEvents() {
  return new EventSource("/api/v1/admin/events")
}
