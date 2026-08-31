# Review report — Worker / 任务

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

---

## 1. Coverage and method

| File | Depth |
|---|---|
| `repositories/tasks.py` | line-read claim/CAS/lease/revive/dedup |
| `tasks/enqueue.py` | line-read |
| `tasks/runner.py` | line-read start/stop/claim/_process/heartbeat/_fail |
| `services/worker_lifecycle.py` | line-read |
| `worker.py` | line-read |
| `api/routes_tasks.py` | line-read |
| `api/routes_tend.py` | line-read |
| `api/routes_settings.py` worker toggle | line-read 790–813 |
| `main.py` lifespan worker boot | line-read |
| `handlers/periodic_tick.py` | line-read dispatch + bootstrap |
| `handlers/recover_stuck_tasks.py` | line-read |
| `handlers/purge_deleted_files.py` | line-read |
| `handlers/delete_storage_object.py` | line-read |
| `handlers/prune.py` | structural scan of targets/retention |
| `maintenance_budget.py` | line-read kind sets |
| `tasks/kinds.py` PERIODIC_INTERVALS / LLM_DEPENDENT_KINDS | line-read |
| `config.py` worker_* defaults | line-read |

Collect-only: `uv run pytest tests/ -k "worker or task_ or runner or tend or purge or maintenance or lifecycle_switch" --collect-only` → **34 selected**. Also opened `test_dispatcher_e2e.py` (recover), `test_task_delivery_fencing_unit.py`, `test_runner_no_llm_key_e2e.py` (not all matched by `-k`).

---

## 2. Regression / re-verify

No Fixed-table item is owned by this child. Default-disabled worker pit is **already fixed**: `config.py:96` `worker_enabled: bool = True`; Settings PUT starts/stops via `worker_lifecycle` (`routes_settings.py:807-810`); tests in `test_worker_web_toggle_e2e.py`.

### L-4 — `claim_pending_ids` docstring undersells CAS

**Still true (docs only).**

`claim_pending_ids` (`repositories/tasks.py:47-50`) still says SQLite has no `FOR UPDATE` so “the caller is expected to be the only worker.”

The actual claim is two-step: select pending ids, then `mark_running` `WHERE status == 'pending' … RETURNING` (`:77-91`). Runner claims one id at a time (`runner.py:198-209`) with a per-delivery `locked_by` nonce. Two SQLite workers can SELECT the same ids; the second `mark_running` returns empty. Fencing tests cover lost-lease heartbeat cancel.

Not a runtime bug. Do not treat as High. Re-filed as **WORKER-L1**.

---

## 3. Findings by severity

### Critical

None.

### High

#### WORKER-H1 — `recover_stuck_tasks` is only a periodic_tick fan-out; crash can deadlock the scheduler or never revive ingest

- **Where:** `runner.py:60-67` start does **not** run recover. `bootstrap_periodic_tick` (`periodic_tick.py:384-387`) no-ops if any **pending or running** tick exists. `recover_stuck_tasks` is only enqueued from `PERIODIC_INTERVALS` inside a successful tick (`kinds.py:119`, `periodic_tick.py:120-158`). `has_inflight_for_kind` includes `running` (`tasks.py:294-305`).
- **Failure scenario A (scheduler deadlock):** `periodic_tick` is claimed and the process dies **before** the self-enqueue at `periodic_tick.py:213-220`. The tick row stays `status=running` with an expired lease. Next worker start: bootstrap sees inflight tick → skips. Nothing is `pending` to claim. Recover is never dispatched (only tick dispatches it). The stuck tick is never revived. **Librarian + recover both stop until a human deletes the running row.**
- **Failure scenario B (ingest-only worker):** `WORKER_SCHEDULER_ENABLED=false`. Bootstrap skips tick (`:375-377`); claim excludes `periodic_tick` (`runner.py:187-191`). Ingest still runs. Worker OOM: `ingest_file` stays `running`. Recover never runs. File stays `processing` until dead-task reconciliation that **also** depends on recover (`recover_stuck_tasks.py:69-75`). `worker.py:16-17` comments claim the next worker will be cleaned by recover_stuck_tasks — that is false in this config.
- **Failure scenario C (no API key):** bootstrap skips tick (`:378-382`). Sweep only marks **pending** LLM kinds dead (`runner.py:87-107`), not **running**. Same stuck-running hole.
- **Suggested fix:** Call `handle_recover_stuck_tasks` (or equivalent) from `TaskRunner.start` **before** bootstrap, unconditionally (not LLM-gated). Treat a `running` tick with an expired lease as not inflight for bootstrap (or always enqueue a due tick if the only inflight tick is stale). Add tests: (1) running expired tick + bootstrap still recovers; (2) scheduler disabled + expired ingest lease revived on start.

### Medium

#### WORKER-M1 — Settings `worker_running` / toggle only see the in-process runner

- **Where:** `worker_lifecycle.is_running()` (`:66-69`); GET settings `worker_running` (`routes_settings.py:171`); PUT toggle (`:807-810`). Documented in `worker_lifecycle.py:10-13`.
- **Failure scenario:** Production split: API with `WORKER_ENABLED=false` + `library-worker` daemon. GUI toggle off writes overlay and stops a runner that was never started; `worker_running` stays false while the daemon keeps claiming. Toggle on starts a **second** in-process worker (two claimers — CAS-safe, but double concurrency and surprising). The page cannot show or stop the daemon.
- **Suggested fix:** Status should be “queue is being claimed” (recent `last_heartbeat_at` / `locked_by`) plus “this process’s runner”. Toggle must not start an in-process runner when a daemon heartbeat is fresh, or must be labeled in-process-only in the GUI. Settings child can own the copy; this child owns the lifecycle lie.

#### WORKER-M2 — `delete_storage_object` TOCTOU between “unreferenced” check and blob delete

- **Where:** `delete_storage_object.py:54-77` — SELECT `File.storage_key`, commit, then `storage.delete` outside the session.
- **Failure scenario:** Purge commits, enqueues delete. Before the handler runs, a new upload reuses the same `storage_key` (mirror path = sanitized folder+name; local UUID keys make this rare). Handler sees no row (or sees the new row and noops — that path is safe). If the new row is inserted **after** the SELECT and **before** delete, the new object is deleted, upload’s DB row points at missing bytes. Window is the queue delay, not microseconds.
- **Suggested fix:** Delete only if `storage_key` still unreferenced **in the same session as a lock**, or include a generation/sha256 in the payload and refuse if the live file’s hash differs. Test: insert a File with that key between the check and delete.

### Low

#### WORKER-L1 — L-4 docstring (re-verified)

- **Where:** `repositories/tasks.py:47-50`.
- **Suggested fix:** Describe the `mark_running` CAS + per-delivery `locked_by`. SQLite multi-worker is supported for claim; Postgres additionally uses `SKIP LOCKED` to avoid extra selects.

#### WORKER-L2 — Recover grace vs heartbeat is fine; interval is 10 minutes on the happy path

- **Where:** lease 60s, heartbeat 20s (`config.py:100-101`); recover grace 10s (`recover_stuck_tasks.py:32`); recover cadence 10 min (`kinds.py:119`).
- **Failure scenario:** none if tick is healthy — a crashed ingest is revived on the next recover (up to ~10 min). Not a bug; operators may think restart is instant (WORKER-H1). No separate fix if H1 lands recover on start.

---

## 4. Checked, no issue

### Claim / CAS / multi-worker

- Select pending then `mark_running` WHERE `status=pending` RETURNING is a real CAS. Per-delivery `locked_by` (`runner.py:214-217`) + heartbeat/mark_done/mark_dead all fence on `worker_id`. Lost lease cancels the handler (`:381-388`, `:284-296`) and does not `_fail` the new owner’s row.
- Postgres `FOR UPDATE SKIP LOCKED` on the select (`tasks.py:59-60`).
- Partial unique index `uq_tasks_active_dedup_key` (`models/tasks.py:26-36`) plus `on_conflict_do_nothing` (`enqueue.py:61-69`).

### Retry

- Attempts incremented on claim. `_fail` retries while `attempts < max_attempts` with exponential backoff capped by settings (`runner.py:35-41, 429-438`). Exhaustion marks dead and calls `mark_file_failed_for_dead_ingest_task`.
- Recover does **not** increment attempts again (`recover_stuck_tasks.py:10-12`).

### Start/stop / default enable

- Default `worker_enabled=True`. Lifespan starts `worker_lifecycle` when enabled (`main.py:92-96`). Settings PUT starts/stops the **in-process** runner without restart. `stop()` sets `_stop`, awaits the loop, then drains `_inflight` (`runner.py:123-129`). Toggle-off does not abandon in-flight handlers (`worker_lifecycle.py:51-53`).
- Split-deploy daemon is a separate process; in-process toggle does not send it SIGTERM (WORKER-M1).

### Recover vs still-running handler

- Heartbeat extends lease while `locked_by` matches. Recover’s UPDATE requires `lease_expires_at == previous_lease` and `< now` (`tasks.py:250-253`). If heartbeat wins, recover no-ops. If recover wins, next heartbeat fails and cancels the handler. `test_dispatcher_e2e.py` and fencing tests cover the intended protocol. Residual is WORKER-H1 (recover never scheduled), not a false-kill of a healthy heartbeat.

### Tend

- Chain order documented. Dedup key is the kind string, same as periodic enqueue (`routes_tend.py:72-86`, `periodic_tick.py:153-157`) — `/tend` reuses in-flight librarian tasks instead of duplicating. Does **not** include recover/purge (user-triggered tidy, not crash recovery).

### Purge / prune / budget

- Purge hard-deletes due entries, then files with no remaining entries, then enqueues `delete_storage_object` after DB commit (intentional). Storage delete failure does not roll back DB.
- Prune only deletes **terminal** task rows (`delete_terminal_batch_before`). Cannot eat running leases.
- `recover_stuck_tasks` is not in `BUDGETED_MAINTENANCE_KINDS` / `LOW_PRIORITY_MAINTENANCE_KINDS` — token budget will not skip recover.

### LLM sweep

- Startup sweep of **pending** LLM-dependent kinds when no key (`runner.py:87-107`). `test_runner_no_llm_key_e2e.py` asserts recover/prune are not swept. Running rows are left for recover (WORKER-H1 if recover never runs).

---

## 5. Test gaps

| Gap | Why |
|---|---|
| Bootstrap with a `running` expired `periodic_tick` | Would catch WORKER-H1 A (scheduler deadlock). |
| `WORKER_SCHEDULER_ENABLED=false` + expired ingest lease + `TaskRunner.start` | WORKER-H1 B. |
| No-key startup with a `running` ingest_file | WORKER-H1 C. |
| Settings `worker_running` while a daemon heartbeat is fresh | WORKER-M1. |
| `delete_storage_object` vs concurrent re-upload of same key | WORKER-M2. |
| L-4 docstring vs two SQLite `TaskRunner`s claiming | Behavior is tested as fencing; docstring is not. |

Dispatcher e2e **does** call `handle_recover_stuck_tasks` directly — it never tests that start/bootstrap will invoke it.

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Run recover_stuck on TaskRunner.start; don’t treat stale running ticks as inflight | `tasks/runner.py`, `periodic_tick.py` bootstrap, recover tests | WORKER-H1 |
| Surface daemon vs in-process worker in settings status | `worker_lifecycle.py`, `routes_settings.py` | WORKER-M1 (may share a settings child) |
| Tighten storage-delete vs new File row | `delete_storage_object.py` | WORKER-M2 |
| Fix claim_pending_ids docstring | `repositories/tasks.py` | WORKER-L1 |

Do not bundle H1 with a scheduler rewrite.

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Claim CAS, retry, fencing, tend dedup, purge/prune boundaries are sound when recover actually runs. Recover is **not** on the start path, so a crashed tick or scheduler-off worker can leave `running` forever (WORKER-H1). |
| **Security** | Task routes are process-auth (cross-cutting). Payload previews on `/tasks/active` are truncated ids/names, not file bytes. Storage delete is keyed; TOCTOU is WORKER-M2. |
| **Architecture** | Lifecycle singleton matches spec (`worker_lifecycle`). Recover as a periodic kind couples crash recovery to the librarian tick — the wrong layer (WORKER-H1). |
| **Spec / contract** | Overlay `worker_enabled` live-toggles in-process runner (accepted). `worker_running` means this process, not “work is happening” (WORKER-M1). L-4 docstring still wrong. |
| **Tests** | Toggle, fencing, no-key pending sweep, dispatcher recover-when-invoked are covered. Start/bootstrap/scheduler-off recovery is not. |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

uv run pytest tests/ -k "worker or task_ or runner or tend or purge or maintenance or lifecycle_switch" --collect-only
# 34 selected / 623 deselected
```
