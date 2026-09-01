# Review report — 设置与配置

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

---

## 1. Coverage and method

| File | Depth |
|---|---|
| `services/config_overlay.py` | line-read allowlist, validate, read/write, merge |
| `config.py` `get_settings` / `resolve_profile` / `resolve_backup` | line-read |
| `api/routes_settings.py` GET/PUT/test/models, `_mask`, `_safe_error` | line-read |
| `llm/factory.py` cache + `reset_clients_cache` | line-read |
| `llm/model_controls.py` | structural (capabilities) |
| `frontend/src/components/LlmProfileEditor.tsx` | line-read mask skip, save, models fetch, default vs profiles |
| `frontend/src/pages/SettingsPage.tsx` worker toggle + missing-key banner | line-read relevant blocks |
| `frontend/src/types/api.ts` `LlmProfileName` / `ServerSettings` | line-read |
| `frontend/src/lib/prefs.ts` | structural (UI prefs, not overlay) |

Collect-only: `uv run pytest tests/ -k "settings or config_validation or llm_" --collect-only` → **87 selected** (noisy `-k`; real owners include `test_settings_routes_e2e.py`, `test_config_validation_unit.py`, `test_llm_*`).

---

## 2. Re-verify L-3 and profile shape

### L-3 — `_mask` leaks API key prefix/suffix

**Still true.**

```99:104:src/library/api/routes_settings.py
def _mask(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 6:
        return "***"
    return f"{secret[:3]}***{secret[-2:]}"
```

GET `/llm` puts this on every profile, backup, overlay `*_api_key` / `*_password`, and `defaults.api_key`. For `sk-…` keys that is `sk-` plus the last two characters.

GUI does **not** write the mask back: `isMaskedKey` skips those fields on save (`LlmProfileEditor.tsx:477-478`) and sends `null` on model-list (`:442`). Direct `PUT /llm` with `api_key: "sk-***ab"` is **not** rejected server-side (`validate_and_normalize` has no mask check) — see SET-M2.

Not re-opened as High. Severity stays Low for the echo; persistence of the mask is SET-M2.

### Frontend `LlmProfileName` vs backend `defaults`

**Not a wire-shape bug.** Backend GET `/llm` returns `profiles` = `{chat, reflect, ingest, vision}` and a separate `defaults` object (`routes_settings.py:324-348`). `LLM_PROFILES_VISIBLE` has no `"default"` (`config.py:451`). Frontend `LlmProfileName = "default" | LlmVisibleProfileName` is the **editor row** type; the default card reads `data.defaults`, others `data.profiles[name]` (`LlmProfileEditor.tsx:348`). Test/models accept `profile=default` via `resolve_profile(..., "default")`.

Docstring on `routes_settings.py:8-9` still lists `audio` on GET `/llm`; audio is not in the visible payload. Low comment drift only.

---

## 3. Findings by severity

### Critical

None.

### High

None on this surface (auth of these routes is cross-cutting).

### Medium

#### SET-M1 — Corrupt overlay is treated as empty; the next merge PUT wipes every other overlay key

- **Where:** `read_overlay` (`config_overlay.py:162-173`) returns `{}` on missing file, JSON error, or non-dict. PUT merge (`routes_settings.py:772-781`) starts from `read_overlay(...)` then writes the result.
- **Failure scenario:** `config_overlay.json` is truncated or hand-edited invalid JSON (or the Windows non-atomic fallback write is interrupted, `:206-214`). GET `/llm` silently shows `.env` defaults — no error. User changes one field (e.g. TPS) and Save (merge, not replace). `merged` is `{llm_default_tps: N}` only. `write_overlay` replaces the file. Chat/ingest keys and every other GUI override disappear. Next ingest uses `.env` or empty keys.
- **Suggested fix:** On JSON parse failure, refuse PUT with 409/500 “overlay unreadable” and log. Optionally keep a `.bak` from the last good write. Do not treat corrupt as empty for merge.

#### SET-M2 — Server will persist a masked placeholder as the real API key

- **Where:** `validate_and_normalize` accepts any string for `*_api_key`. Models endpoint strips `***` (`routes_settings.py:683-685`); PUT does not.
- **Failure scenario:** Non-GUI client (or a future form bug) PUTs `llm_default_api_key: "sk-***xy"` copied from GET. Overlay stores that string. `resolve_profile` uses it; chat/test fail with invalid key. GUI would have skipped the field.
- **Suggested fix:** Reject values containing `***` (or matching `_mask` output) on write, same as models. Test: PUT masked key → 422, overlay unchanged.

### Low

#### L-3 / SET-L1 — Mask still shows first 3 + last 2

- **Where:** `routes_settings.py:99-104`.
- **Suggested fix:** Last-4-only, or `api_key_set` boolean with no echo. GUI already has `api_key_set`.

#### SET-L2 — GET `/llm` module docstring still mentions audio

- **Where:** `routes_settings.py:8-9` vs `LLM_PROFILES_VISIBLE`.
- **Suggested fix:** Drop audio from the GET blurb (audio is intentionally not overlay-writable).

#### SET-L3 — Overlay allowlist omits `ocr_max_pages` / `worker_scheduler_enabled` / CORS/Host

- **Where:** `_ALLOWED_FIELDS`. Instant-effect story: GUI cannot change OCR cap (AM-1, ingest child) or scheduler. Not a settings bug; record so Settings copy does not claim “all knobs are live.”

---

## 4. Checked, no issue

### Overlay vs env priority

- `get_settings` loads `.env` then `merge_overlay_into_settings` (`config.py:769-780`). Overlay wins per key. Blank/`None` on disk is dropped on read (`:185-187`) so it cannot null out `.env`. PUT `null` pops the key (`routes_settings.py:775-777`) — “clear override” works.

### What becomes live after Save

- PUT always `get_settings.cache_clear()` + `reset_clients_cache()` (`:784-785`). Next `get_chat_client` rebuilds. Embedding/rerank factories are **not** lru_cached; they read `get_settings()` each call.
- `worker_enabled` also starts/stops the in-process runner (worker child owns the daemon gap).
- `worker_batch_size` is read per claim (`TaskRunner._current_settings`).
- Not live / not in overlay: `OCR_MAX_PAGES` (AM-1), `worker_scheduler_enabled`, Host/CORS, storage/db.

### LLM test / models

- Test uses `resolve_profile` + `get_chat_client`; timeout bounded; `retry=False` on probe. `_safe_error` redacts the exact key substring.
- Models accept unsaved form overrides; masked `api_key` is ignored so the stored key is used. Unknown profile → 422.

### Secrets

- GET never returns raw keys (`_mask` / `api_key_set`). Overlay dump masks `*_api_key` and `*_password`. GET `/server` has `embedding_api_key_set` / `rerank_api_key_set` only. WebDAV password is overlay-only and masked on GET `/llm`.
- Unknown PUT fields → 422, not silent drop. Read path drops unknown keys (hand-edited junk).

### Worker toggle UI

- Settings page writes `worker_enabled` and shows `worker_running` (`SettingsPage.tsx:1329-1348`). Warns when enabled but not running. Lifecycle semantics: worker child (WORKER-M1).

### Allowlist vs GET `/server`

- Server snapshot is a large resolved view (including retry seconds, compaction, document vision). Extra keys vs an older handwritten `ServerSettings` are now `components["schemas"]["ServerSettingsResponse"]` (`api.ts:360-365`). Remaining drift is OpenAPI `dict` leftovers — frontend-pages child.

---

## 5. Test gaps

| Gap | Why |
|---|---|
| Merge PUT after unreadable overlay JSON | SET-M1. |
| PUT `llm_default_api_key` equal to a `_mask` value | SET-M2. |
| Assert GET `/llm` `profiles` has no `"default"` key and `defaults` is present | Documents the shape the editor depends on. |
| Corrupt overlay GET does not 500 | Today it silently falls back — if SET-M1 is fixed, test the 409. |

`test_settings_routes_e2e.py` covers models listing, unconfigured backup, overlay write. Mask format and merge-after-corrupt are untested.

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Title | Files | Why |
|---|---|---|
| Refuse merge PUT when overlay JSON is unreadable | `config_overlay.py`, `routes_settings.py` | SET-M1 |
| Reject masked api_key on PUT | `validate_and_normalize` | SET-M2 |
| Tighten `_mask` to last-4 or boolean-only | `routes_settings.py` | L-3 / SET-L1 |

Do not mix with AM-1 (OCR cap) or WORKER-M1 (daemon status).

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | Overlay merge, cache bust, test/models, GUI mask-skip, default vs profile rows are sound. Corrupt overlay + merge PUT can delete all GUI overrides (SET-M1). |
| **Security** | Keys are not returned in full. Mask still leaks 5 characters (L-3). PUT will store a mask string if a client sends it (SET-M2). `_safe_error` only redacts the exact key. Route auth is cross-cutting. |
| **Architecture** | Allowlist + atomic overlay file is the right split from `.env`. `reset_clients_cache` is wired on PUT. Audio profile correctly excluded from overlay until a pipeline exists. |
| **Spec / contract** | Wire shape is `profiles` + `defaults`, not `profiles.default`. Frontend editor matches. GET `/llm` docstring still says audio. |
| **Tests** | Settings e2e and config validation exist. Corrupt-overlay merge and masked-key PUT are gaps. |

---

## Verification

```
git status --short -- src tests frontend openapi
# clean

uv run pytest tests/ -k "settings or config_validation or llm_" --collect-only
# 87 selected / 570 deselected
```
