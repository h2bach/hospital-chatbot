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
      images: [],
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
  it("returns the answer and an empty citation list when none are provided", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ response: "Đã nhận yêu cầu." }),
    } as Response)

    await expect(sendMessage("session-1", "Lịch bác sĩ tuần này")).resolves.toEqual({
      answer: "Đã nhận yêu cầu.",
      citations: [],
    })

    expect(fetchMock).toHaveBeenCalledWith(
      "/c/session-1",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    )
  })

  it("normalizes citations returned alongside the answer", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          response: "Giá khám là 500.000 đồng [1](#citation-cit_1).",
          citations: [
            {
              id: "cit_1",
              index: 1,
              source_kind: "rag_document",
              title: "Bảng giá dịch vụ",
              excerpt: "Giá khám: 500.000 đồng",
              highlight_ranges: [{ start: 0, end: 5 }],
              match_status: "exact",
              confidence: 0.92,
              context_available: true,
            },
            { title: "Thiếu id nên bị loại" },
          ],
        }),
    } as Response)

    const result = await sendMessage("session-2", "Giờ làm việc của bệnh viện?")

    expect(result.citations).toEqual([
      expect.objectContaining({ id: "cit_1", index: 1, title: "Bảng giá dịch vụ" }),
    ])
  })
})
