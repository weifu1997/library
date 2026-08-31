# Error Handling

> How errors are handled in this project.

---

## Overview

<!--
Document your project's error handling conventions here.

Questions to answer:
- What error types do you define?
- How are errors propagated?
- How are errors logged?
- How are errors returned to clients?
-->

(To be filled by the team)

---

## Error Types

<!-- Custom error classes/types -->

(To be filled by the team)

---

## Error Handling Patterns

<!-- Try-catch patterns, error propagation -->

(To be filled by the team)

---

## API Error Responses

<!-- Standard error response format -->

(To be filled by the team)

---

## Common Mistakes

### Chat Stop must cancel by conversation id, not session id

`POST /v1/conversations/{conversation_id}/cancel` looks up a `Conversation`
row and cancels `_ACTIVE_TURNS[conversation_id]`. The chat session id is a
different identifier. Posting the session id returns 404; the durable turn
keeps running.

The client must send the id from the SSE `conversation` event. While that
event has not arrived, wait (`pendingCancel`) instead of aborting the
stream first. Keep `streaming` true until cancel actually fires so Send
cannot start a second turn against the same session lock.

`cancelChat` must throw on any non-OK response, including 404. A finished
turn whose Conversation still exists returns 202 `{cancelled: false}` —
that is success. 404 means the id was wrong or the row is gone.

Regression: `tests/test_chat_cancel_e2e.py`.

---

## Scenario: Chat cancel

### 1. Scope / Trigger
- Trigger: GUI Stop / any client that must halt `_run_durable_turn`

### 2. Signatures
- `POST /v1/conversations/{conversation_id}/cancel` → 202 `{conversation_id, cancelled}` or 404
- Frontend: `cancelChat(conversationId: string): Promise<void>`

### 3. Contracts
- Path param is Conversation.id from SSE event `conversation` (`data` = id string)
- `_ACTIVE_TURNS` is keyed by that same conversation id
- 202 `cancelled: true` — in-flight task cancelled
- 202 `cancelled: false` — conversation exists, no live task
- 404 — no Conversation row for that id

### 4. Validation & Error Matrix
- Unknown id → 404
- Live turn + matching id → 202 cancelled true, later `error` frame is `CLIENT_STOPPED_MESSAGE`
- Live turn + session id → 404, turn continues
- Non-OK HTTP in `cancelChat` → throw (do not treat 404 as success)

### 5. Good/Base/Bad Cases
- Good: Stop after `conversation` event → cancel that id
- Base: Stop before `conversation` event → `pendingCancel`, cancel when the event arrives
- Bad: `cancelChat(sessionId)` and ignore 404

### 6. Tests Required
- Session-id cancel 404s and the durable task is still running
- Conversation-id cancel 202s, task leaves `_ACTIVE_TURNS`, no later `answer`

### 7. Wrong vs Correct
#### Wrong
```typescript
void cancelChat(sessionId); // 404 swallowed, turn keeps running
if (!response.ok && response.status !== 404) throw ...
```
#### Correct
```typescript
void cancelChat(live.conversationId); // Conversation.id from SSE
if (!response.ok) throw new Error(`chat cancellation failed: ${response.status}`);
```
