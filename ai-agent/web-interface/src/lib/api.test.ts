import { afterEach, describe, expect, it, vi } from "vitest"
import { normalizeSession, normalizeSessionList, sendMessage, sendMessageStream } from "./api"

afterEach(() => {
  vi.restoreAllMocks()
})

describe("API response normalizers", () => {
  it("normalizes the current uppercase Go session response", () => {
    const session = normalizeSession({
      Session: {
        ID: "session-1",
        Title: "Kiểm tra thời gian",
        OwnerID: "",
        Context: {
          Messages: [
            { Role: "User", Content: "Mấy giờ ở Hà Nội?" },
            { Role: "Assistant", Content: "Bây giờ là 20:00." },
          ],
          Tools: [{ Name: "checkTime" }],
        },
      },
    })

    expect(session.id).toBe("session-1")
    expect(session.messages).toHaveLength(2)
    expect(session.messages[1]).toEqual({
      role: "Assistant",
      content: "Bây giờ là 20:00.",
    })
    expect(session.tools).toHaveLength(1)
  })

  it("also accepts a future lowercase JSON response", () => {
    const session = normalizeSession({
      session: {
        id: "session-2",
        title: "Lowercase",
        owner_id: "user-1",
        context: {
          messages: [{ role: "tool", content: "Tool output" }],
          tools: [],
        },
      },
    })

    expect(session).toMatchObject({
      id: "session-2",
      ownerId: "user-1",
      title: "Lowercase",
    })
    expect(session.messages[0].role).toBe("Tool")
  })

  it("drops malformed list entries while preserving valid sessions", () => {
    expect(
      normalizeSessionList({
        sessions: [
          { id: "one", owner_id: "", title: "Một" },
          null,
          { title: "Không có ID" },
        ],
      }),
    ).toEqual([{ id: "one", ownerId: "", title: "Một" }])
  })
})

describe("sendMessage", () => {
  it("sends the selected access role in the Role header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ response: "Đã nhận yêu cầu." }),
    } as Response)

    await expect(
      sendMessage("session-1", "Lịch bác sĩ tuần này", "GUEST"),
    ).resolves.toEqual({ answer: "Đã nhận yêu cầu.", suggestions: [] })

    expect(fetchMock).toHaveBeenCalledWith(
      "/c/session-1",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Role: "GUEST",
        }),
      }),
    )
  })

  it("defaults to GUEST when a role is not supplied", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ response: "Đã nhận yêu cầu." }),
    } as Response)

    await sendMessage("session-2", "Giờ làm việc của bệnh viện?")

    expect(fetchMock).toHaveBeenCalledWith(
      "/c/session-2",
      expect.objectContaining({
        headers: expect.objectContaining({ Role: "GUEST" }),
      }),
    )
  })

  it("normalizes at most five verified approximate choices", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        response: "Có phải ý của bạn là...",
        suggestions: [
          { id: "E1", label: "SPECT/CT Tetrofosmin", value: "Mã 19.0069.1829", similarity: 0.95 },
          { id: "E2", label: "Ứng viên yếu", value: "Không chọn", similarity: 0.79 },
        ],
      }),
    } as Response)

    await expect(sendMessage("session-3", "Terofomin")).resolves.toEqual({
      answer: "Có phải ý của bạn là...",
      suggestions: [{
        id: "E1",
        label: "SPECT/CT Tetrofosmin",
        value: "Mã 19.0069.1829",
        similarity: 0.95,
      }],
    })
  })
})

describe("sendMessageStream", () => {
  it("parses ordered status, verified deltas, suggestions and completion", async () => {
    const encoded = new TextEncoder().encode([
      'event: status\ndata: {"phase":"planning","label":"Đang phân tích"}\n\n',
      'event: delta\ndata: {"text":"Câu trả "}\n\n',
      'event: delta\ndata: {"text":"lời đã duyệt."}\n\n',
      'event: suggestions\ndata: {"items":[{"id":"E1","label":"SPECT/CT","value":"19.0069.1829","similarity":0.95}]}\n\n',
      'event: complete\ndata: {"response":"Câu trả lời đã duyệt.","suggestions":[{"id":"E1","label":"SPECT/CT","value":"19.0069.1829","similarity":0.95}]}\n\n',
    ].join(""))
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(encoded)
          controller.close()
        },
      }),
    } as Response)
    const statuses: string[] = []
    const deltas: string[] = []

    await expect(sendMessageStream("session-4", "Câu hỏi", {
      onStatus: ({ label }) => statuses.push(label),
      onDelta: (text) => deltas.push(text),
    })).resolves.toEqual({
      answer: "Câu trả lời đã duyệt.",
      suggestions: [{ id: "E1", label: "SPECT/CT", value: "19.0069.1829", similarity: 0.95 }],
    })
    expect(statuses).toEqual(["Đang phân tích"])
    expect(deltas.join("")).toBe("Câu trả lời đã duyệt.")
  })
})
