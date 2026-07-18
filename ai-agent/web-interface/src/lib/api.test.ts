import { afterEach, describe, expect, it, vi } from "vitest"
import { normalizeSession, normalizeSessionList, sendMessage } from "./api"

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
            {
              Role: "Assistant",
              Content: "Bây giờ là 20:00.",
              Suggestions: [{ ID: "E1", Label: "Mục đúng", Value: "Chọn mục đúng", Similarity: 0.91 }],
            },
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
      images: [],
      suggestions: [{ id: "E1", label: "Mục đúng", value: "Chọn mục đúng", similarity: 0.91 }],
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
  it("sends images with the device-isolation header and returns suggestions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        response: "Đã nhận yêu cầu.",
        suggestions: [{ id: "E1", label: "Kết quả", value: "Chọn kết quả", similarity: 0.9 }],
      }),
    } as Response)

    await expect(
      sendMessage("session-1", "Đọc ảnh này", [{ mimeType: "image/png", data: "cG5n" }]),
    ).resolves.toEqual({
      answer: "Đã nhận yêu cầu.",
      suggestions: [{ id: "E1", label: "Kết quả", value: "Chọn kết quả", similarity: 0.9 }],
    })

    expect(fetchMock).toHaveBeenCalledWith(
      "/c/session-1",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-Device-ID": expect.any(String),
        }),
        body: JSON.stringify({ message: "Đọc ảnh này", images: [{ mime_type: "image/png", data: "cG5n" }] }),
      }),
    )
  })

  it("sends a text-only request without access-role headers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ response: "Đã nhận yêu cầu." }),
    } as Response)

    await sendMessage("session-2", "Giờ làm việc của bệnh viện?")

    expect(fetchMock).toHaveBeenCalledWith(
      "/c/session-2",
      expect.objectContaining({
        headers: expect.not.objectContaining({ Role: expect.anything() }),
        body: JSON.stringify({ message: "Giờ làm việc của bệnh viện?", images: [] }),
      }),
    )
  })
})
