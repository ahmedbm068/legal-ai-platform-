import { describe, it, expect } from "vitest";
import { compactChatStateForStorage } from "./chatStorage";
import type { ChatMessage } from "./types";

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    role: "user",
    content: "hello",
    createdAt: new Date().toISOString(),
    ...overrides,
  } as ChatMessage;
}

describe("compactChatStateForStorage", () => {
  it("drops sessions for non-numeric case keys", () => {
    const state = {
      sessionsByCase: {
        // @ts-expect-error — exercising the runtime guard for malformed keys
        notANumber: [
          { id: "s1", title: "x", createdAt: "", updatedAt: "", messages: [] },
        ],
      },
      activeSessionIdByCase: {},
    };
    const result = compactChatStateForStorage(state);
    expect(result.sessionsByCase).toEqual({});
  });

  it("limits sessions per case to the standard cap and keeps the most recent", () => {
    const sessions = Array.from({ length: 12 }).map((_, idx) => ({
      id: `s${idx}`,
      title: `session ${idx}`,
      createdAt: new Date(2024, 0, idx + 1).toISOString(),
      updatedAt: new Date(2024, 0, idx + 1).toISOString(),
      messages: [],
    }));
    const state = {
      sessionsByCase: { 42: sessions },
      activeSessionIdByCase: { 42: "s11" },
    };

    const result = compactChatStateForStorage(state);
    expect(result.sessionsByCase[42]).toHaveLength(6);
    // Most-recent first.
    expect(result.sessionsByCase[42][0].id).toBe("s11");
    expect(result.activeSessionIdByCase[42]).toBe("s11");
  });

  it("falls back to the newest session when the active id no longer exists", () => {
    const sessions = Array.from({ length: 8 }).map((_, idx) => ({
      id: `s${idx}`,
      title: `session ${idx}`,
      createdAt: new Date(2024, 0, idx + 1).toISOString(),
      updatedAt: new Date(2024, 0, idx + 1).toISOString(),
      messages: [],
    }));
    const state = {
      sessionsByCase: { 7: sessions },
      activeSessionIdByCase: { 7: "deleted-session" },
    };

    const result = compactChatStateForStorage(state);
    expect(result.activeSessionIdByCase[7]).toBe("s7");
  });

  it("trims long message bodies and limits message count per session", () => {
    const longBody = "x".repeat(20_000);
    const messages = Array.from({ length: 100 }).map((_, idx) =>
      makeMessage({ id: `m${idx}`, content: longBody })
    );
    const state = {
      sessionsByCase: {
        1: [
          {
            id: "only",
            title: "t",
            createdAt: "",
            updatedAt: "",
            messages,
          },
        ],
      },
      activeSessionIdByCase: { 1: "only" },
    };

    const result = compactChatStateForStorage(state);
    const compactedSession = result.sessionsByCase[1][0];
    expect(compactedSession.messages.length).toBeLessThanOrEqual(36);
    for (const msg of compactedSession.messages) {
      expect(msg.content.length).toBeLessThanOrEqual(6000);
    }
  });

  it("aggressive mode further reduces caps", () => {
    const sessions = Array.from({ length: 8 }).map((_, idx) => ({
      id: `s${idx}`,
      title: "t",
      createdAt: new Date(2024, 0, idx + 1).toISOString(),
      updatedAt: new Date(2024, 0, idx + 1).toISOString(),
      messages: Array.from({ length: 30 }).map((__, j) => makeMessage({ id: `m${j}` })),
    }));
    const state = {
      sessionsByCase: { 9: sessions },
      activeSessionIdByCase: { 9: "s7" },
    };

    const result = compactChatStateForStorage(state, true);
    expect(result.sessionsByCase[9]).toHaveLength(3);
    expect(result.sessionsByCase[9][0].messages.length).toBeLessThanOrEqual(14);
  });
});
