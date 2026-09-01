# Review: Agent / chat / citations

Report-only. No product code, tests, configs, OpenAPI, or frontend were modified.

## 1. Coverage and method (line-read vs pattern-scan)

### Line-read

| Surface | Range | Notes |
|---|---|---|
| `src/library/agent/runtime.py` `run_turn` | 737–1100 | Fully line-read. |
| `src/library/agent/runtime.py` `_run_execute_phase` | 2081–2757 | Fully line-read (budget, finalization, pairing handoff, truncation). |
| `src/library/agent/runtime.py` `_dispatch_tool_calls` | 2899–3561 | Fully line-read (preflight, waves, drain, pairing, doom-loop). `_run_tool` 3564–3585 also line-read. |
| `runtime.py` citation rewrite | 1555–2076 | Locator vs source text, PDF/Office deep-links. |
| `runtime.py` plan/budget helpers | 1104–1552 | Session name, NO_PLAN, `_fit_provider_messages`. |
| `agent/tools/query_sql.py` | entire file | Security surface. |
| `agent/tools/read_files.py` | entire file | Security surface + compression hook. |
| `agent/tools/analyze_container.py` | entire file | Security surface (path, regex, glob). |
| `agent/tools/query_log.py` | entire file | Regex subprocess, size caps. |
| `agent/tools/finish_research.py` | entire file | |
| `agent/tools/generate_chart.py` | entire file | Vega construction / `__user_only__`. |
| `agent/citation_manifest.py` | entire file | Quote/page verification. |
| `agent/conversation_compaction.py` | 1–150, 358–429 | TokenCounter + `_atomic_message_groups`. |
| `api/routes_chat.py` | entire file | Durable turn, SSE replay, cancel. |
| `api/routes_agent.py` | entire file | Sessions, transcript, attachments. |
| `citations.py` | entire file | |
| `frontend/src/api/chatStream.ts` | entire file | SSE reconnect regression. |
| `frontend/src/pages/ChatPage.tsx` | 1–340, 660–774 | send/stop/event reducer. |
| `frontend/src/lib/chatSession.ts` | entire file | |
| `frontend/src/components/TurnView.tsx` | 1–120 | Types + citation navigation. |
| `frontend/src/components/SessionList.tsx` | 1–80 | |
| `tasks/handlers/reflect_turn.py` | 1–200, 250–399 | Invalidation allowlist. |
| `tasks/handlers/summarize_session.py` | 1–150, 240–420 | Supersede path. |
| `llm/anthropic_adapter.py` | 141–226 | tool_use / tool_result render. |
| `llm/openai_adapter.py` | 194–278 | Same. |
| `agent/tool_locks.py`, `tool_scheduler.py` | entire / 1–80 | |
| `pipelines/archive.py` `read_segment` | 287–325 | `member_path` vs listable set. |
| `storage/decompress.py` | 1–40, bomb-limit comments | 200 MB post-extract cap. |

### Structural scan (not every line)

- Remaining tools: `search_metadata`, `search_journal`, `recall_knowledge`, `list_folder`, `list_catalogs`, `read_catalog`, `read_entries_metadata`, `resolve_tag`, `materialize_view` — schema + handler entry + SQL/path usage.
- `runtime.py` 1–736 (constants, truncation, vision probe).
- `read_compression.py`, `compression_adapter.py`, `stable_context.py` (docstring + imports), `cache_metrics.py`, `tool_display.py`, `text_query.py`, `_regex_subprocess.py`.
- `llm/factory.py` retry policy, `prompt_cache.py`, `tagged_response.py`.
- `frontend/src/types/api.ts` ChatEvent / transcript types.
- Tests matching the collect filter (names + a sample of pairing/budget/citation tests).

`run_turn`, `_run_execute_phase`, and `_dispatch_tool_calls` were **fully line-read**. No ranges inside those three were skipped.

### Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Two High bugs: Stop posts the session id to `/conversations/{id}/cancel` (CHAT-H1); `user_artifact` is emitted and typed but never applied in Chat (CHAT-H2). Medium: auto-budget treats failed tool dicts as new evidence (CHAT-M1). Pairing, the cancel route given a real conversation id, SSE cursor, NO_PLAN / empty execute, and per-session locks: no issue (see §4). |
| **Security** | `query_sql` keyword denylist is a UX false-positive, not RCE (CHAT-M2). Container / archive reads can OOM on a large compressed blob before the 200 MB extract cap (CHAT-M3). Path traversal, DuckDB `enable_external_access=false` + lock, `generate_chart` XSS/SSRF, citation quote checks, regex subprocess, attachment path, reflect/summarize ID allowlists: no issue (see §4). |
| **Architecture / maintainability** | AL-1 dead `dup_prior` arm; AL-2 wrong exhausted-turn log field; CHAT-L1 no-tool nudge unbudgeted; CHAT-L2 unused `read_files` diagnostics; CHAT-L3 session routes import private runtime helpers; A-1 `runtime.py` still ~3585 lines. |
| **Spec / contract** | `user_artifact` is in OpenAPI / `ChatEventType` / `KNOWN_EVENTS` but absent from `applyEventToTurnList`, `Turn` / `TurnView`, and `GET /sessions/{id}/messages` (CHAT-H2). Keeping tools in the request when `tools_disabled` is intentional cache-stability. |
| **Tests** | See §5. No frontend test runner. No Stop→conversation-id test, no `user_artifact` UI test, no `{ok: False}` budget-upgrade test, no `SELECT REPLACE` / `LIKE '%DROP%'` test, no compressed-archive size-cap test. Collect-only: 148 selected, 0 skipped. |

## 2. Regression check of M-2 / M-3 / L-5 / L-6

Fix child: `08-31-fix-chat-stream-resume`. Current `frontend/src/api/chatStream.ts` still contains the fix.

| ID | Status | Evidence |
|---|---|---|
| **M-2** (transient SSE errors reported immediately) | **Still fixed** | `lastTransientError` at 59–66; `onError` only at 75–80 after attempts exhaust. A recovered drop does not call `onError`. |
| **M-3** (events without `event_cursor` re-published on resume) | **Still not a real bug** | `_replay_frames` (`routes_chat.py:451–457`) always sets `"id": str(row.cursor)`. Client still skips `eventCursor <= cursor` (`chatStream.ts:124`) as defense. No extra client-side fingerprint was added; that matches the fix-child PRD. |
| **L-5** (abort listener leak on timeout) | **Still fixed** | `reconnectDelay` (`chatStream.ts:159–163`) `removeEventListener` on the timer path. |
| **L-6** (abandoned body not cancelled) | **Still fixed** | `cancelBody` at 93–100, called from the catch at 72. |

No SSE reconnect regression. Do not re-open M-2/M-3/L-5/L-6.

### Re-verify still-open prior items

| ID | Status |
|---|---|
| **AL-1** `finish_research` `dup_prior` dead | **Still true.** Preflight at `runtime.py:3059` excludes `finish_research` from `dup_prior`. Sync branch at 3081–3085 is unreachable. |
| **AL-2** exhausted-turn log prints wrong max | **Still true.** Loop bound is `max_total_turns` (2154–2158); log at 2741–2742 prints `max_execute_turns`. |

## 3. Findings by severity

### Critical

None.

### High

#### CHAT-H1 — Stop button cancels the session id, not the conversation id; the durable turn keeps running

`frontend/src/pages/ChatPage.tsx:250` plus `frontend/src/api/chatStream.ts:167–174` plus `src/library/api/routes_chat.py:499–511`.

```242:251:frontend/src/pages/ChatPage.tsx
  const stop = useCallback(() => {
    const { sessionId } = useChatSession.getState();
    ...
    void cancelChat(sessionId);
```

`cancelChat` POSTs `/v1/conversations/{id}/cancel`. The route loads a **Conversation** row. Stop passes the **session** UUID. Those are different tables. The handler 404s. `cancelChat` treats 404 as success (`chatStream.ts:172`).

Aborting the fetch only stops `_replay_frames`. `_run_durable_turn` is a background task (`routes_chat.py:247–261`, confirmed by `test_chat_background_turn_does_not_depend_on_stream_consumption`). `_ACTIVE_TURNS` is keyed by conversation id (`routes_chat.py:346`), so the 404 path never `task.cancel()`.

`stop()` also `liveStreams.delete(sessionId)` (`ChatPage.tsx:247–248`) **before** `send()`’s `finally` (`325–336`). That `finally` only marks `done: true` when the live entry is still present, so Stop does **not** mark the turn done. `TurnView` `inFlight` stays true (`!turn.done && !turn.error`). What *does* change is `setStreaming(false)` (`251`): the Stop button becomes Send.

**Failure scenario:** User clicks Stop mid-turn. The Stop button disappears. The turn accordion still shows “in progress”. `cancelChat(sessionId)` 404s and is treated as success. The agent continues calling the LLM and writing `agent_events`. Because `streaming` is already false, the next send is allowed; the server blocks on `_turn_lock` until the “stopped” turn finishes. Reloading the session after that shows a completed answer the user thought they cancelled. Tokens keep burning until timeout/`done`.

The conversation id is already on the turn after the `conversation` event (`ChatPage.tsx:684`, `Turn.conversationId`).

**Fix:** Call `cancelChat(live.turns[live.turnIdx].conversationId)` (wait if the conversation event has not arrived). Mark the live turn done/error locally in `stop()` (do not rely on `send()`’s `finally` after deleting the live entry). Do not treat cancel 404 as success when the client still believes the turn is live. Add an API/e2e test that Stop hits `/conversations/{conversation_id}/cancel` and the background task is cancelled.

#### CHAT-H2 — `user_artifact` is persisted and typed, then dropped on the floor in the GUI

Runtime emits `user_artifact` at `runtime.py:3401–3410` for `generate_chart` (`vega_lite`) and `query_sql` `export_csv` (`data_export`). OpenAPI/`ChatEventType`/`KNOWN_EVENTS` include the event. CLI at least updates a spinner (`cli/commands.py:1024–1038`).

`applyEventToTurnList` (`ChatPage.tsx:673–774`) has no `user_artifact` case (falls through to `default: return turn`). `Turn` / `TurnView` have no artifact field. `GET /sessions/{id}/messages` (`routes_agent.py:437–464`) never returns `__user_only__` / chart spec / export path.

**Failure scenario:** User asks for a chart. `generate_chart` succeeds, SSE carries the Vega-Lite spec, CLI says “chart ready”, the web UI shows only a tool-call row (preview `"chart"` from `tool_display.py:581–586`). Same for `export_csv`: the CSV is written under `LIBRARY_HOME/exports` and never offered as a download. Session replay (`replayedToTurn`, `ChatPage.tsx:968–1010`) rebuilds the same tool-call row from the transcript preview — still no Vega viewer or file link. The tool’s documented purpose (“render a chart for the user”) does not happen in the primary UI.

**Fix:** Handle `user_artifact` in the live reducer; persist a denormalized artifact list on the transcript; render Vega-Lite (or a download link) in `TurnView`. Reconstruct from `tool_calls[].result.__user_only__` for old rows.

### Medium

#### CHAT-M1 — Auto-budget upgrade counts failed tool results as “new evidence”

`runtime.py:3351–3354` computes `result_ok` (false when `ok is False` or `error` is set) but only uses it for `finish_research` stats. At 3420–3421 every non-exception, non-`finish_research` handler return increments `stats.successful_new_results`. `_try_upgrade_budget` (`1230–1256`) upgrades auto mode when that counter is `> 0`. The same branch hard-codes SSE `"ok": True` (`3428`) even when `result_ok` is false, so `applyEventToTurnList` / `markResult` (`ChatPage.tsx:747`) paints the step green while the preview may say `error: …`.

**Failure scenario:** Auto/quick plan, model calls `search_metadata` / `read_files` with bad ids. Tools return `{"ok": False, "error": "entry not found"}` (no exception; `read_files.py:297` and several other handlers). Each call counts as success and the GUI step is marked ok. Near the last round the budget upgrades quick→standard→deep (`AUTO_MAX_BUDGET_UPGRADES = 2`). The user pays for a long doomed search. `test_auto_mode_uses_planner_budget_and_upgrades_on_new_evidence` only scripts a counting tool that returns success (`test_chat_quick_mode_e2e.py:138–144`).

**Fix:** Increment `successful_new_results` only when `result_ok` is true (and, if desired, when the payload is non-empty). Emit SSE `ok` from `result_ok`. Add a unit test with `{ok: False}` that asserts no upgrade.

#### CHAT-M2 — `query_sql` keyword denylist matches identifiers and string literals

`query_sql.py:55–58` and `_validate_sql` at 188–190. `\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|COPY|PRAGMA|EXPORT|INSTALL|LOAD|SET|TRUNCATE|GRANT|REVOKE|MERGE|REPLACE)\b` runs on the raw SQL with no comment/string stripping.

**Failure scenario:** Legitimate SELECTs are rejected with “only read-only SELECT statements are allowed”:

- `SELECT REPLACE(name, '-', '_') FROM t1`
- `SELECT * FROM t1 WHERE note LIKE '%DROP TABLE%'` (SQL audit CSV)
- `SELECT copy FROM t1` (column named `copy`)

DuckDB is already in-memory with `enable_external_access=false` + `lock_configuration=true` after load (`397–400`, lock is applied immediately before model SQL at 309), so the denylist is a UX filter, not the real sandbox. Tests (`test_duckdb_tools_e2e.py:173–178`) assert `DROP TABLE t1` is rejected; the file docstring also mentions INSERT/UPDATE, but those statements are not asserted. There is no test that `SELECT REPLACE(...)` / `LIKE '%DROP%'` survive.

**Fix:** Parse with sqlglot/DuckDB’s parser, or strip string literals and `--` / `/* */` comments before the keyword scan. Keep the dangerous-function regex and the external-access lock.

#### CHAT-M3 — Container tools load the entire compressed object before the 200 MB extract cap

`analyze_container.py:146–148` and archive `read_segment` via `_read_all` (`pipelines/archive.py:329–333`) accumulate `storage.get(...)` into a `bytearray` with no compressed-size cap. `open_archive` then enforces `DEFAULT_BOMB_LIMIT_BYTES = 200MB` **after** extraction (`storage/decompress.py:36–38`).

**Failure scenario:** User has a multi-GB zip (compressed). Agent calls `analyze_container` or `read_files` with `member_path`. The process reads the whole blob into RAM, then may still fail the extract cap. One such tool call can OOM the API worker. `query_log` already caps at 32 MB (`query_log.py:29`); `query_sql` caps per file at 200 MB (`query_sql.py:51`) but allows 50 files.

**Fix:** Stream to a size-capped temp file (or abort when `Content-Length` / running byte count exceeds a setting) before `open_archive`. Reuse the bomb limit for compressed input too.

### Low

#### AL-1 — `finish_research` `dup_prior` branch is dead (re-verified)

`runtime.py:3059` vs `3078–3085`. Not a runtime bug; maintainers may think duplicate `finish_research` is deduped. Delete the `finish_research` arm or `assert tc.name != "finish_research"`.

#### AL-2 — Exhausted-turn warning logs `max_execute_turns` not `max_total_turns` (re-verified)

`runtime.py:2741–2742`. Operators tune execute budget after seeing `hit agent_execute_max_turns=8` when the loop actually exhausted continuations/finalization/malformed-repair quota.

#### CHAT-L1 (prior AL-3) — `PREMATURE_NO_TOOL_NUDGE` is not in `max_total_turns`

`max_total_turns` at 2154–2158 adds quick retries, finalization attempts, and malformed repairs. `no_tool_repair_used` at 2494–2500 and 2632–2644 consumes a loop iteration without extra quota. A repaired researching turn gets one fewer execute round than advertised. Small, inconsistent accounting.

#### CHAT-L2 — `read_files` diagnostic helpers are unused in production

`_locator_diagnostic` / `_segment_diagnostic` / `_error_diagnostic` (`read_files.py:425–516`) are only called from `tests/test_read_files_diagnostics_unit.py`. `_safe_read_segment` (518–532) still returns `exc!r` to the model. Either wire the diagnostics into logs or drop the dead helpers.

#### CHAT-L3 — Session routes import private runtime helpers

`routes_agent.py:25–27` imports `_public_plan_text`, `_rewrite_footnotes_for_display`, `_strip_session_name_line`. Transcript rendering is coupled to agent internals. Extract a small `agent/display.py` (or similar) if runtime is split (A-1).

#### A-1 — `runtime.py` still ~3585 lines

`run_turn` ~360 lines, `_run_execute_phase` ~680, `_dispatch_tool_calls` ~660, plus citation locators. Matches the prior oversized-function note. Not a current functional failure.

## 4. Explicit “checked, no issue” list

- **tool_use / tool_result pairing (Anthropic):** `_dispatch_tool_calls` fills `placeholders` in source order; SSE is completion order. Fatal failure drain (`3475–3541`) emits explicit errors for unstarted calls and batch followers. Doom-loop nudge mutates the last real block rather than forging a `tool_use_id` (`3548–3561`). Compaction `_atomic_message_groups` (`conversation_compaction.py:358–395`) keeps assistant tool-use with following `role=tool` messages. Adapters map `ToolResultBlock.tool_call_id` → Anthropic `tool_use_id` / OpenAI `tool_call_id`. Covered by `test_fatal_tool_failure_stops_later_waves` and `test_compaction_preserves_atomic_tool_exchange_and_critical_context`.
- **Keeping tools in the request when `tools_disabled`:** Intentional for prompt-cache stability (`runtime.py:2335–2338`). Tests assert `tool_choice == "auto"` on final rounds. Disabled calls are rejected before dispatch.
- **`query_sql` sandbox (aside from CHAT-M2):** Parameterized loads; table names `t{n}`; `enable_external_access=false` + `lock_configuration=true` before model SQL; semicolon / non-SELECT start rejected; `read_csv_auto(` etc. blocked. Not treated as RCE.
- **Path traversal in containers:** `analyze_container` and archive `read_segment` require `path in visible` after `_is_listable` (rejects `..`, absolute, unsafe basenames). `open_archive` bomb cap 200 MB extracted. Covered by `test_container_e2e`.
- **`read_files` `member_path`:** Same listable set; no pipeline dispatch on missing members.
- **`generate_chart` XSS/SSRF:** Server-built spec only; no `data.url` / expressions; field whitelist. (GUI still does not render it — CHAT-H2.)
- **Citation locator vs source:** `prepare_finish_citation_manifest` requires quote in successful `read_files` text (`citation_manifest.py:68–78`). PDF live rewrite drops unmatched quotes from the query string (`runtime.py:2058–2059`). Office locators use `quote_matches_source_text`. Replay can skip source reads (`locate_pdf_quotes=False`) by design.
- **Reflect invalidation:** `reflect_turn.py:266–277` only applies ids from the prior-note candidate list.
- **Summarize supersede:** `filter_active_insight_ids` requires an existing active insight UUID; guessing a UUID is not a realistic attack. Prompt-listed priors being superseded is intentional.
- **Cancel API itself:** Given a real conversation id, `cancel_chat_turn` cancels `_ACTIVE_TURNS` and `_finish_interrupted_turn` persists `error`. The bug is the GUI argument (CHAT-H1), not the route.
- **SSE event cursor:** Resume uses `after_cursor`; frames always have `id`. Client dedupes by cursor. `Last-Event-ID` honored on the resume route.
- **Per-session serialisation:** asyncio lock + Postgres advisory lock + `UNIQUE(session_id, turn_index)`. Documented; SQLite relies on the asyncio lock.
- **NO_PLAN repair / empty execute:** Repairs local-library NO_PLAN; empty execute yields `error` rather than a fake answer (`run_turn:980–987`).
- **Image attachments:** Saved off the LLM tape; serve path rejects traversal (`routes_agent.py:260–276`). Caps enforced in `post_chat` before SSE.
- **Regex ReDoS:** `query_log` / `analyze_container` search run in a killable subprocess with timeout (`_regex_subprocess.py`).
- **Vision probe:** Ambiguous 400 is not cached as “no vision”; transient errors assumed capable.

## 5. Test-gap list

- **No frontend test runner** (already recorded in the SSE fix PRD). `chatStream.ts` reconnect, Stop, and `user_artifact` have zero assertions.
- **No test that `POST /conversations/{id}/cancel` is called with a conversation id** from the GUI, or that a session id 404s and the background task keeps running.
- **No test that the Chat UI (or transcript) surfaces `user_artifact`.** `test_generate_chart_e2e.py` only checks the SSE frame exists.
- **No test that `{ok: False}` tool results do not trigger auto-budget upgrade** (CHAT-M1).
- **No `query_sql` test that `SELECT REPLACE(...)` / `LIKE '%DROP%'` is allowed** (CHAT-M2). DuckDB e2e is a `test_script_main` bundle.
- **No compressed-archive size-cap test** for `analyze_container` / archive `read_segment` (CHAT-M3).
- **`read_files` diagnostic unit tests never execute production logging** (CHAT-L2) — tautological relative to the handler.
- **AL-2 log text is untested.**
- Collect-only for the implement.md filter (`agent or chat or citation or session or tool or compression or runtime`) currently reports **148 collected / 509 deselected / 0 skipped**. Skip reasons were not an issue on this collect.

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| `fix-chat-stop-cancels-conversation` | `frontend/src/pages/ChatPage.tsx`, `frontend/src/api/chatStream.ts`, cancel e2e | CHAT-H1: Stop must cancel the durable turn. |
| `fix-chat-user-artifact-ui` | `ChatPage.tsx`, `TurnView.tsx`, `routes_agent.py` transcript, maybe a small Vega viewer | CHAT-H2: charts/exports are invisible in the GUI. |
| `fix-auto-budget-failed-tools` | `src/library/agent/runtime.py`, `tests/test_chat_quick_mode_e2e.py` | CHAT-M1: do not upgrade on error payloads; emit SSE `ok` from `result_ok`. |
| `fix-query-sql-keyword-filter` | `src/library/agent/tools/query_sql.py`, duckdb tests | CHAT-M2: stop rejecting valid SELECTs. |
| `cap-container-compressed-bytes` | `analyze_container.py`, `pipelines/archive.py` | CHAT-M3: bound RAM before extract. |
| `cleanup-runtime-dead-budget-logs` (optional, with A-1 split) | `runtime.py` | AL-1 / AL-2 / CHAT-L1 while extracting execute/dispatch. |
