/** SSE consumer for POST /v1/chat/{session_id}.
 *
 *  EventSource doesn't support POST bodies, so we use fetch() with a
 *  manual reader and parse SSE frames ourselves. The CLI does the same
 *  thing in Python (cli/client.py); this is the JS counterpart.
 *
 *  Frame format the server emits (sse_starlette default):
 *      event: <type>\n
 *      data: <payload>\n
 *      \n
 *  Payloads are typically JSON, sometimes plain strings (errors). We
 *  pass each frame through onEvent with the raw text so callers can
 *  decide how to decode per type.
 */
import type { ChatEvent, ChatEventType, ChatImage, ChatMode } from "@/types/api";
import { authHeaders, getBaseUrl, resolveTauriBaseUrl } from "@/api/client";

export interface ChatStreamOptions {
  signal?: AbortSignal;
  mode?: ChatMode;
  /** Per-turn image attachments. Raw base64 (no `data:` prefix). Sent only
   *  with this live turn — never re-sent on resumed/historical turns. */
  images?: ChatImage[];
  onEvent: (ev: ChatEvent) => void;
  onError?: (err: unknown) => void;
}

export async function streamChat(
  sessionId: string,
  query: string,
  opts: ChatStreamOptions,
): Promise<void> {
  if (!getBaseUrl()) await resolveTauriBaseUrl();
  const initialUrl = `${getBaseUrl()}/v1/chat/${encodeURIComponent(sessionId)}`;
  let res = await fetch(initialUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...authHeaders(),
    },
    body: JSON.stringify({
      query,
      mode: opts.mode ?? "auto",
      ...(opts.images?.length ? { images: opts.images } : {}),
    }),
    signal: opts.signal,
  });
  await assertStreamResponse(res);

  let conversationId: string | undefined;
  let cursor = 0;
  let terminal = false;
  for (let attempt = 0; attempt < 4 && !terminal; attempt += 1) {
    try {
      const state = await consumeResponse(res, opts, { conversationId, cursor });
      conversationId = state.conversationId;
      cursor = state.cursor;
      terminal = state.terminal;
    } catch (error) {
      if (opts.signal?.aborted) throw error;
      opts.onError?.(error);
    }
    if (terminal) break;
    if (!conversationId || attempt >= 3) {
      throw new Error("chat stream ended before the turn completed");
    }
    await reconnectDelay(250 * (2 ** attempt), opts.signal);
    const resumeUrl = `${getBaseUrl()}/v1/conversations/${encodeURIComponent(conversationId)}`
      + `/events?after_cursor=${cursor}`;
    res = await fetch(resumeUrl, {
      headers: { Accept: "text/event-stream", ...authHeaders() },
      signal: opts.signal,
    });
    await assertStreamResponse(res);
  }
}

async function assertStreamResponse(res: Response): Promise<void> {
  if (res.ok && res.body) return;
  let detail = `${res.status}`;
  try { detail = (await res.text()) || detail; } catch { /* ignore */ }
  throw new Error(`chat stream failed: ${detail}`);
}

async function consumeResponse(
  res: Response,
  opts: ChatStreamOptions,
  initial: { conversationId?: string; cursor: number },
): Promise<{ conversationId?: string; cursor: number; terminal: boolean }> {
  if (!res.body) throw new Error("chat stream has no response body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let conversationId = initial.conversationId;
  let cursor = initial.cursor;
  let terminal = false;

  const publish = (ev: ChatEvent | null) => {
    if (!ev) return;
    if (ev.eventCursor && ev.eventCursor <= cursor) return;
    if (ev.eventCursor) cursor = ev.eventCursor;
    if (ev.type === "conversation" && typeof ev.data === "string") {
      conversationId = ev.data;
    }
    ev.conversationId = conversationId;
    if (ev.type === "done" || ev.type === "error") terminal = true;
    opts.onEvent(ev);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = indexOfDelim(buffer)) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx).replace(/^(\r?\n){2}/, "");
      publish(parseFrame(frame));
    }
  }
  if (buffer.trim()) publish(parseFrame(buffer));
  return { conversationId, cursor, terminal };
}

async function reconnectDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

export async function cancelChat(conversationId: string): Promise<void> {
  if (!getBaseUrl()) await resolveTauriBaseUrl();
  const response = await fetch(
    `${getBaseUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/cancel`,
    { method: "POST", headers: authHeaders() },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(`chat cancellation failed: ${response.status}`);
  }
}

function indexOfDelim(s: string): number {
  const a = s.indexOf("\n\n");
  const b = s.indexOf("\r\n\r\n");
  if (a === -1) return b;
  if (b === -1) return a;
  return Math.min(a, b);
}

const KNOWN_EVENTS: ReadonlySet<ChatEventType> = new Set([
  "conversation",
  "planning",
  "plan",
  "thinking",
  "tool_call",
  "tool_result",
  "answer",
  "error",
  "done",
]);

function parseFrame(frame: string): ChatEvent | null {
  // "event:" / "data:" / ":" comments. Multiple `data:` lines are
  // concatenated with newlines per the SSE spec.
  let evType = "message";
  let eventCursor: number | undefined;
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const field = line.slice(0, colon);
    const value = line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") evType = value;
    else if (field === "id" && /^\d+$/.test(value)) eventCursor = Number(value);
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0 && evType === "message") return null;
  const raw = dataLines.join("\n");
  const type = (KNOWN_EVENTS.has(evType as ChatEventType) ? evType : "message") as ChatEventType;
  return { type, data: tryJson(raw), raw, eventCursor };
}

function tryJson(s: string): unknown {
  if (!s) return s;
  const t = s.trim();
  if (!t) return s;
  if (t[0] !== "{" && t[0] !== "[" && t[0] !== '"') return s;
  try { return JSON.parse(s); } catch { return s; }
}
