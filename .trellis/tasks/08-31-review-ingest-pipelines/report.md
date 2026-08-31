# Review report — ingest pipelines

Parent: `08-31-feature-code-review`. Report-only. No product code was modified.

## 1. Coverage and method

### In-scope files

| File | Depth |
|---|---|
| `src/library/pipelines/registry.py` | line-read (140 lines) |
| `src/library/pipelines/base.py` | line-read (156 lines) |
| `src/library/pipelines/pdf.py` | **line-read entire 2612 lines** (see ranges below) |
| `src/library/pipelines/pdf_text.py` | line-read (281 lines) |
| `src/library/pipelines/_text_indexer.py` | line-read (683 lines) |
| `src/library/pipelines/_long_index.py` | line-read (387 lines) |
| `src/library/pipelines/docx.py` | line-read `run` / vision / `_slice` / coverage; structural scan of XML walk helpers |
| `src/library/pipelines/pptx.py` | line-read `run` / `_slice` / coverage / image extract; structural scan of shape walk |
| `src/library/pipelines/spreadsheet.py` | line-read `run` / `read_segment` / `_render_workbook` |
| `src/library/pipelines/image.py` | line-read |
| `src/library/pipelines/document_vision.py` | line-read |
| `src/library/pipelines/text.py` | line-read `run` / chunked index / `read_segment` / decode; structural scan of heading-scan helpers |
| `src/library/pipelines/log.py` | line-read |
| `src/library/pipelines/archive.py` | line-read `run` / `read_segment` / `_is_listable` / peek |
| `src/library/pipelines/email.py` | line-read |
| `src/library/pipelines/markitdown.py` | line-read |
| `src/library/pipelines/git_metadata.py` | line-read |
| `src/library/pipelines/__init__.py` | line-read (registration imports) |
| `src/library/tasks/handlers/ingest_file.py` | line-read (389 lines) |
| `src/library/services/ingest_status.py` | line-read (50 lines) |
| `src/library/storage/decompress.py` | line-read `open_archive` (zip-slip / bomb) — supporting, not owned |
| `src/library/services/user_files.py` `_coverage_summary` | line-read (backend coverage projection) |

### `pdf.py` ranges (required)

AH-2 lives in `_ocr_pdf_pages` + `_coverage`. Every other path is called out here.

| Lines | Path | Depth |
|---|---|---|
| 1–91 | module constants, **AM-1** `OCR_MAX_PAGES = get_settings().ocr_max_pages` | line-read |
| 92–221 | prompts, `PdfNeedsOcrError`, registration | line-read |
| 226–351 | `PdfPipeline.run`: text-layer extract, scanned-PDF OCR dispatch, figure describe, single vs chunked index | line-read |
| 353–375 | `_read_bytes`, `_page_count`, `_needs_chunked_index` | line-read |
| 376–475 | `_run_single_index` (empty-summary hard-fail) | line-read |
| 476–673 | `_run_chunked_index` / `_iter_prompt_chunks` (**INGEST-H1**) | line-read |
| 674–765 | `_result_from_fields`, `_coverage` (AH-2 `ocr_failed_pages` / `indexed_partial`) | line-read |
| 771–938 | `read_segment` + `_answer_with_vlm` (OCR stored text vs live render) | line-read |
| 939–1065 | `_slice_ocr_text` | line-read |
| 1066–1260 | `_slice` / `_slice_text_layer` (default 20-page window, pattern cap 200) | line-read |
| 1262–1300 | `_extract_text`, `_truncate`, legacy renderer | line-read |
| 1348–1646 | OCR payload/classify/caps (`_ocr_configured_page_cap`, `_ocr_pages_to_process`) | line-read |
| 1648–1794 | PDF vision question batches / JPEG budget | line-read |
| 1796–1888 | `_ocr_pdf_pages` (**AH-2** None vs `""`; **AM-2** per-batch render) | line-read |
| 1898–2128 | `_render_pdf_pages_to_jpeg` handle close, scan-scale cap, JPEG fit | line-read |
| 2149–2372 | `extract_images` / `describe_images` / figure inline | line-read |
| 2384–2612 | `_resolve_pdf_page_window`, `_clamp_pdf`, `_pdf_pattern_search` | line-read |

No `pdf.py` function was left as “unscanned”. Functions over ~200 lines (`run` 226–351, `_run_chunked_index` 476–644, `read_segment` 771–804 + callees, `_ocr_pdf_pages` 1796–1888, `_slice_text_layer` 1095–1260) were line-read.

### Pattern scan (all in-scope modules)

Grep for `except Exception`, `asyncio.gather`, path join, `read_bytes` without cap, `indexed_partial` / `partial_reasons`, `OCR_MAX_PAGES`, `open_archive`.

### Tests inspected

Collect-only (command in §Verification): **111 selected, 1 skipped at collection** (`tests/test_rar_e2e.py` module-level skip when no `rar` CLI). Also opened/ grepped PRD-listed modules that the `-k` filter only partially hits: `test_document_vision_unit.py`, `test_ingest_file_unit.py`, `test_ingest_status_reconciliation.py`, `test_pdf_ocr_uncapped_unit.py`, `test_ingest_coverage_surface_unit.py`, `test_git_repo_e2e.py`, `test_container_e2e.py`.

Did **not** claim “100% tests / no skips”.

---

## 2. Regression (AH-2) and re-verify (AM-1, AM-2)

### AH-2 — OCR per-page failure swallowed; file marked success

**Status: still fixed. Do not re-open.**

Fix child `08-31-fix-ocr-partial-failure` is still present:

- `_ocr_pdf_pages` documents three states and returns `None` for a failed page, `""` for a blank successful page, and pads past the cap with `""` (`pdf.py:1796–1888`). After retries the failure path `return`s without writing `out[i]`, so the slot stays `None` (`pdf.py:1851–1857`).
- `PdfPipeline.run` counts `failed_ocr_pages`, logs them, and appends `ocr_page_failures` to `partial_reasons` (`pdf.py:273–305`).
- `_coverage` sets `indexed_partial` if `ocr_failed_pages > 0` even when `indexed_pages == total_pages`, and records `ocr_failed_pages` (`pdf.py:743–765`).
- Backend projection still exposes `indexed_partial`, `ocr_failed_pages`, `partial_reasons` (`user_files.py:236–274`). Frontend display is out of scope; the backend fields can still express partial failure.
- Regression tests still exist and assert the original failure scenario no longer holds: `test_ocr_failed_page_is_none_not_blank`, `test_coverage_marks_partial_on_ocr_failures`, `test_ocr_pages_past_cap_are_blank_not_failed` in `tests/test_pdf_ocr_uncapped_unit.py`.

Original failure (rate-limited pages stored as blank, ingest `done` with a hole) does not hold on current code.

### AM-1 — `OCR_MAX_PAGES` evaluated at import

**Status: still true.**

```91:91:src/library/pipelines/pdf.py
OCR_MAX_PAGES: int | None = get_settings().ocr_max_pages
```

`_ocr_configured_page_cap` reads that module constant, not live settings (`pdf.py:1619–1625`). `get_settings` is `@lru_cache` (`config.py:769–781`) and Settings PUT calls `cache_clear()`, but that cannot refresh a value already copied into `pdf.OCR_MAX_PAGES` at import.

`ocr_max_pages` is **not** in `config_overlay._ALLOWED_FIELDS`, so the Settings GUI cannot write it today. The live-settings hole is still real for: process start after `.env` change is the only way to change the cap; any future overlay/GUI wiring of this key would also be dead until restart unless the constant is replaced with a `get_settings()` read. Tests monkeypatch `pdf_module.OCR_MAX_PAGES` precisely because the value is frozen (`test_pdf_ocr_uncapped_unit.py`, `test_pdf_ocr_cap_e2e.py`).

### AM-2 — each OCR batch re-parses the whole PDF

**Status: still true.**

```1872:1878:src/library/pipelines/pdf.py
    for start in range(0, pages_to_ocr, OCR_RENDER_BATCH_PAGES):
        batch_count = min(OCR_RENDER_BATCH_PAGES, pages_to_ocr - start)
        page_jpegs = await asyncio.to_thread(
            _render_pdf_pages_to_jpeg,
            pdf_bytes,
            batch_count,
            start_page=start,
        )
```

`_render_pdf_pages_to_jpeg` always constructs a new `pdfium.PdfDocument(pdf_bytes)` (`pdf.py:1911`) even when `start_page > 0`. `OCR_RENDER_BATCH_PAGES = 20` (`pdf.py:96`). Default cap 300 pages ⇒ 15 full parses of the same byte blob per scanned ingest. Page/bitmap/PIL handles are closed in `finally` (`pdf.py:1919–1926`, `1943–1951`) — no handle leak found; the cost is CPU/parse, not an unclosed handle.

---

## 3. Findings by severity

No Critical. AH-2 is not listed here (still fixed).

### High

#### INGEST-H1 — native PDF/text chunked index: one chunk LLM failure fails the whole ingest

- **Where:** `src/library/pipelines/pdf.py:535-566`; `src/library/pipelines/text.py:369-409`
- **Contrast (already correct):** `src/library/pipelines/_text_indexer.py:315-332` catches per-chunk `Exception`, degrades to a heuristic section, and continues. Office/email/markitdown/log go through that helper. PDF and the text pipeline reimplemented chunking without the degrade path.
- **Failure scenario:** User uploads a 61+ page PDF (`_needs_chunked_index` when pages > `MAX_PAGES` (60) or rendered text > `MAX_TOTAL_TEXT_BYTES` (80_000)) or a text file > `MAX_TEXT_BYTES` (60_000 chars). Ingest splits into page/line chunks and `asyncio.gather`s LLM calls with no `return_exceptions` and no per-chunk `try`. One chunk hits a 429/500 after client retries. `gather` raises, `handle_ingest_file` `_mark_failed(..., reason="pipeline_exception")`, file is `failed`. Already-paid OCR/extraction work is discarded. A 2-page docx with the same LLM blip would ingest as heuristic sections and `done`.
- **Suggested fix:** Copy `_text_indexer._index_chunk`’s try/except + `fallback_section` into `PdfPipeline._run_chunked_index` and `TextPipeline._run_chunked_index`. On any degraded chunk, set `indexed_partial` and append `chunk_index_failures` to `partial_reasons`. Wrap the aggregate call the same way `_text_indexer.py:413-432` already does (PDF aggregate at `pdf.py:614-628` and text aggregate at `text.py:441-468` currently have no try).

### Medium

#### AM-1 — `OCR_MAX_PAGES` import-time (still-open prior)

- **Where:** `src/library/pipelines/pdf.py:91`, `pdf.py:1619-1620`
- **Failure scenario:** Operator sets `OCR_MAX_PAGES=50` in `.env` (or, later, overlay) and expects the running worker to cap the next scanned ingest. `pdf.OCR_MAX_PAGES` still holds the value from process start (default 300). A 200-page scan still fans out 200 VLM calls.
- **Suggested fix:** `_ocr_configured_page_cap` should call `get_settings().ocr_max_pages` (runtime). Keep a test-only setter if needed; do not seed a module constant from settings at import. If the cap should be GUI-writable, add `ocr_max_pages` to overlay `_ALLOWED_FIELDS` in a settings-owned follow-up.

#### AM-2 — each OCR batch re-parses the whole PDF (still-open prior)

- **Where:** `src/library/pipelines/pdf.py:1872-1878` + `pdf.py:1911`
- **Failure scenario:** 300-page scanned PDF at default cap. Ingest opens the same `pdf_bytes` with pypdfium2 15 times, re-walking the xref each batch. On large scans this dominates wall time before any VLM call, and spikes CPU on the worker.
- **Suggested fix:** Open `PdfDocument` once per `_ocr_pdf_pages` (or per ingest), render batches from the live handle, close in an outer `finally`. Keep `to_thread` so the event loop stays free.

#### INGEST-M1 — git branch name from `HEAD` is used as a filesystem path

- **Where:** `src/library/pipelines/git_metadata.py:105-110` (branch taken from `ref: refs/heads/<name>`), `121`, `140`
- **Failure scenario:** User ingests a zip that contains `.git/HEAD` with `ref: refs/heads/../../../../../../../etc/passwd`. `parse()` is called on the extract root (`archive.py:409-412`). `_parse_branch_tip` does `git_dir / "refs" / "heads" / meta.branch` and `read_text()` if `is_file()`. Pathlib resolves `..`. First line of an arbitrary worker-readable file is stored as `head_hash` in `files.description.git_metadata` (and thus in search/agent context). Trigger is an untrusted archive, not a trusted generated id.
- **Suggested fix:** Reject branch names containing `/`, `\`, or `..`. Resolve `ref_path` and require `ref_path.resolve().is_relative_to(git_dir.resolve())` before read.

#### INGEST-M2 — spreadsheet `read_segment` materializes every row with no cap

- **Where:** `src/library/pipelines/spreadsheet.py:81` → `_extract_read_text` → `_render_read_from_bytes` (`186-188`) → `_iter_rows(..., None)` (`226`)
- **Failure scenario:** Agent `read_files` on a 200k-row × 40-col xlsx (ingest itself only samples 200 rows — that path is fine). Read path sets `read_full=True`, no `hard_limit`, no `MAX_CELL_CHARS`. Worker builds one giant string; a wide finance export can OOM or stall the worker for minutes. `tests/test_read_files_contract_unit.py` currently *requires* full rows, so this is intentional contract vs missing bound.
- **Suggested fix:** Keep ingest sampling. For read, stream/window by `offset`/`max_chars` or a hard row cap (e.g. 10k) with `truncated` + `next_offset` extras, matching PDF’s default 20-page window.

#### INGEST-M3 — archive ingest never writes `coverage` / `indexed_partial`

- **Where:** `src/library/pipelines/archive.py:249-284` (`description` has tree/peeks, no `coverage` key)
- **Failure scenario:** Zip with 400 members. Ingest peeks at most 8 (`PEEK_MEMBERS_MAX`, `archive.py:54,484-486`), marks the file `done`. `_coverage_summary` returns `None` (`user_files.py:257-258`) because there is no `description.coverage`. UI/agent cannot tell this archive was sampled. PDF/text/office/log all set `indexed_partial` + `partial_reasons` for the analogous cap.
- **Suggested fix:** Add `coverage: {unit: members, total_units, indexed_units: len(peeks), indexed_partial, partial_reasons: ["archive_peek_cap"]}` and a retrieval extra line. Peek failures already become `"[peek failed: ...]"` strings (`archive.py:517-519`) — count those as partial too.

#### INGEST-M4 — text-layer PDF page extract failure stored as a blank page

- **Where:** `src/library/pipelines/pdf_text.py:80-83`
- **Failure scenario:** Native-text PDF, one page’s content stream throws in pypdf. That page becomes `""`. `PdfPipeline.run` treats it as “no text on this page”, does not increment a failure counter, and does not add a `partial_reasons` entry (AH-2 only covers the OCR path). A 20-page report with a broken page 7 is indexed and marked complete; the hole looks like a genuinely empty page.
- **Suggested fix:** Return a sentinel (or parallel `failed_pages` list) from `extract_pdf_text_range`, and have `_coverage` set `indexed_partial` + `text_page_failures` the same way OCR does.

#### INGEST-M5 — image vision-index failure is stored as a successful metadata-only ingest

- **Where:** `src/library/pipelines/image.py:210-229` (catch → `_metadata_only_image_result`), `472-498`
- **Failure scenario:** Vision profile is configured but the VLM call fails or returns no `<summary>`. Ingest still returns a `PipelineResult` and the handler writes `ingest_status=done`. Coverage is `{source_mode: image_metadata_only, reason: vision_index_failed}` with **no** `indexed_partial`. `_coverage_summary` therefore omits the failure unless `indexed_partial` is a bool. The Library panel shows a completed image with summary `Image file: foo.png`.
- **Suggested fix:** Set `indexed_partial: true` and `partial_reasons: [reason]` on the metadata-only coverage dict so the existing whitelist surfaces it.

### Low

#### INGEST-L1 — `ArchivePipeline.read_segment` opens its own DB session

- **Where:** `src/library/pipelines/archive.py:336-351`
- **Failure scenario:** `read_segment` calls `get_session_factory()` to look up `display_name` so py7zz sees the right suffix. Pipelines are documented as DB-free (`base.py:3-6`). Nested sessions from a tool call can see a different isolation level than the request session; tests that stub storage but not the engine get surprising queries. Fallback to `original_ext` already exists (`349-351`).
- **Suggested fix:** Pass `display_name` / filename in from the handler/tool (file_row or args). Delete the pipeline-layer session.

#### INGEST-L2 — ingest folder-path walk has no cycle guard

- **Where:** `src/library/tasks/handlers/ingest_file.py:244-254`
- **Failure scenario:** If a `folders` cycle exists (AH-1 blocked WebDAV import cycles; other writers are owned by library-org), `_resolve_folder_path` loops until the worker is killed. Ingest task never leaves `processing` until dead-task reconciliation.
- **Suggested fix:** Same visited-id set used in the WebDAV folder-cycle fix.

#### INGEST-L3 — persist-phase exceptions do not call `_mark_failed` locally

- **Where:** `src/library/tasks/handlers/ingest_file.py:134-148` (try/except covers only `pipeline.run`)
- **Failure scenario:** Pipeline succeeds, `_persist` raises (`file/entry vanished mid-ingest` at `267-268`, or catalog/tag flush error). `ingest_status` stays `processing` until the runner/recover handler calls `mark_file_failed_for_dead_ingest_task` (`ingest_status.py:18-49`, used from `runner.py` and `recover_stuck_tasks.py`). Window is “processing” with no live worker. Reconciliation exists, so this is not High.
- **Suggested fix:** Wrap phase 3 in the same `_mark_failed` + re-raise as phase 2.

#### INGEST-L4 — `pdf.py` is an oversized module (prior A-1)

- **Where:** `src/library/pipelines/pdf.py` (2612 lines: ingest, OCR, vision Q&A, figure extract, read_segment)
- **Failure scenario:** none currently; maintainability only. Matches prior A-1 “oversized functions in … pdf”.
- **Suggested fix:** Split OCR/render, read_segment, and figure-describe into sibling modules. Do not bundle with AM-1/AM-2/INGEST-H1 fixes.

---

## 4. Checked, no issue

Explicit passes (silence is not a pass):

- **AH-2 OCR swallow:** still fixed (see §2). Not re-opened.
- **Partial failure vs `done`:** by design, `ingest_status` is `done` whenever the pipeline returns. Distinguishing signal is `description.coverage.indexed_partial` + `partial_reasons` + `ocr_failed_pages`. Backend `_coverage_summary` whitelists those fields (`user_files.py:236-274`; tests in `test_ingest_coverage_surface_unit.py`). PDF OCR cap (`ocr_page_cap`), text byte cap, log sample, office prompt/slide/row caps all set the flag.
- **PDF handles / temp during OCR render:** `PdfDocument`, page, bitmap, and PIL image are closed in `finally` (`pdf.py:1912-1926`, `1936-1951`, `2087-2088`). No leak found on the render path.
- **Zip slip / path traversal on archive members:** `open_archive` records `unsafe_basenames` for `..` / absolute / drive-letter entries (`decompress.py:223-228`). `_is_listable` rejects `..`, absolute, drive letters, and those basenames (`archive.py:354-373`). `read_segment` only reads `member_path` if it is in the filtered visible set (`archive.py:306-315`). Bomb cap 200 MB (`decompress.py:36,230-251`).
- **Archive image members at ingest:** VLM is skipped; placeholder only (`archive.py:500-507`). Agent can still drill via `read_segment_from_bytes`.
- **Decompression tempdir:** `open_archive` `shutil.rmtree` in `finally` (`decompress.py:295-296`). MarkItDown temp file unlinked in `finally` (`markitdown.py:160-172`).
- **PDF vision JPEG budget:** pages are downscaled and quality-looped under `PDF_VISION_MAX_DATA_URL_CHARS` (`pdf.py:2040-2088`, `1772-1793`). Question text is bounded (`1749-1765`).
- **Document-embedded images:** `MAX_DOCUMENT_VISION_IMAGES = 20` (`document_vision.py:24,74-83`). Per-image failures skip that image, do not fail ingest (`118-125`).
- **Image ingest without vision:** metadata-only result, file stays readable (`image.py:159-167`, tests in `test_image_pipeline_unit.py`).
- **`ingest_file` write-once:** content fields written only if `ingested_at is None` (`ingest_file.py:271-276`); status still set `done`. Deleted file skipped (`70-73`). Already-`done` skipped (`74-77`). Missing pipeline → `_mark_failed` + raise (`130-132`). Pipeline exception → `_mark_failed` + raise (`135-140`). Dead ingest tasks mirrored by `mark_file_failed_for_dead_ingest_task` (`ingest_status.py`; tests in `test_ingest_status_reconciliation.py`).
- **Semantic index refresh failure:** swallowed after ingest `done`, audited (`ingest_file.py:169-199`). Intentional; search-owned.
- **Registry precedence:** `.log` `ext_overrides_mime` beats `text/plain` (`registry.py:105-115`, `log.py:71-81`). SVG → text (`__init__.py` import order + `text.py` mime `image/svg+xml`). Legacy `.doc`/`.ppt` not registered (`test_pipeline_registry_unit.py`).
- **`_text_indexer` soft-fail:** empty body heuristic; LLM exception → heuristic result (`_text_indexer.py:122-178`). Office formats inherit this.
- **Log/text byte caps on ingest:** `MAX_LOG_BYTES` 50 MiB (`log.py:42,254-259`); `MAX_TEXT_INDEX_BYTES` 8 MiB (`text.py:64,701-712`).
- **Email HTML:** stdlib `HTMLParser`, no file/network. Attachments listed by name/size, not decoded into the index (`email.py:214-226`).
- **ReDoS via `pattern`:** agent-supplied regex compiled with `IGNORECASE|MULTILINE` in several `read_segment` helpers. Not treated as a finding: the caller is the local agent tool, not an unauthenticated HTTP surface (upload HTTP is out of scope).
- **PDF `files.kind = "text"`** (`pdf.py:716`): content kind (text-shaped), consistent with docx/pptx also using `kind="text"` via `_text_indexer`. Not a bug.
- **Whole-blob slurp** (PDF/email/markitdown/archive `_read_all`): same pattern as other ingest; size bound is the upload/storage cap (owned by `review-upload-scan-sync`).

---

## 5. Test-gap list

Collect-only: `uv run pytest tests/ -k "ingest or pdf or office or pipeline or email or archive or markitdown" --collect-only` → 111 selected, 1 skipped.

| Gap | Evidence |
|---|---|
| `test_rar_e2e.py` skipped at collection when no `rar` CLI | `tests/test_rar_e2e.py:59-67` (`pytest.skip(..., allow_module_level=True)`). This is the **1 skipped** item. Runtime RAR *decode* via bundled 7zz is untested on this host. |
| `handle_ingest_file` status transitions untested as a unit | `test_ingest_file_unit.py` only covers `_persist` tag dedupe. No unit test for: missing `file_id`, deleted skip, already-`done` skip, `no_live_entry` → `failed` without raising, `no_pipeline` → `_mark_failed` + raise, pipeline exception mapping, persist exception leaving `processing`. Happy path is e2e-only (`test_ingest_e2e.py`). |
| INGEST-H1 untested | `test_long_document_indexing_unit.py` covers PDF/text chunk+aggregate happy path, not a failing middle chunk. `_text_indexer` degrade path has no sibling test for `PdfPipeline._index_chunk`. |
| AM-1 untested as a product behavior | Tests monkeypatch `pdf.OCR_MAX_PAGES`; nothing asserts that `get_settings.cache_clear()` does **not** change the cap (the bug) or that a live read would (the fix). |
| AM-2 untested | `test_ocr_pdf_pages_batches_full_uncapped` checks batch *count*, not that `PdfDocument` is constructed once vs per batch. |
| INGEST-M1 untested | No git_metadata test with `ref: refs/heads/../...`. |
| INGEST-M2 untested as a bound | `test_read_files_contract_unit.py::test_spreadsheet_read_uses_full_rows_not_ingest_sample` encodes unbounded read. No row/memory cap test. |
| INGEST-M3 untested | Archive e2e asserts `ingest_status == done`, not coverage/partial. |
| INGEST-M4 untested | `test_pdf_text_read_unit.py` does not inject a throwing page extract. |
| INGEST-M5 untested | Image unit tests cover missing vision profile, not VLM exception → `indexed_partial`. |
| `list_members` | `Pipeline.list_members` default `None` (`base.py:148-155`); `ArchivePipeline` does not override. No test expects it. Agent uses `analyze_container` instead — contract drift, not a failing test. |
| E2e `test_script_main` wrappers | Several PDF/image/archive e2e modules expose a single `test_script_main`. They are real scripts with assertions, not empty tests; they are coarse (one process, many checks). |

No assertion-free tests were found in the opened unit modules. No `pytest.mark.skip` besides the rar module-level skip.

---

## 6. Suggested follow-up fix children

Do **not** create these in this round.

| Suggested title | Owning files | Why |
|---|---|---|
| Fix OCR_MAX_PAGES to read settings at runtime (AM-1) | `pipelines/pdf.py`; unit test that `cache_clear()` changes the cap | Small, independently verifiable. Do not mix with AM-2 or pdf.py split. |
| Reuse one PdfDocument across OCR render batches (AM-2) | `pipelines/pdf.py` `_ocr_pdf_pages` / `_render_pdf_pages_to_jpeg` | Perf-only; keep handle-close tests. |
| Degrade PDF/text chunk index on per-chunk LLM failure (INGEST-H1) | `pipelines/pdf.py`, `pipelines/text.py`; mirror `_text_indexer.py` | User-visible failed ingest on long docs. |
| Sanitize git ref paths in git_metadata (INGEST-M1) | `pipelines/git_metadata.py` | Path traversal from untrusted archive. |
| Bound spreadsheet read_segment rows (INGEST-M2) | `pipelines/spreadsheet.py`; update `test_read_files_contract_unit.py` | Worker OOM/stall on large xlsx reads. |
| Archive + image coverage partial flags (INGEST-M3, INGEST-M5) | `pipelines/archive.py`, `pipelines/image.py` | Same coverage contract as PDF/office. |
| Record text-layer PDF page extract failures (INGEST-M4) | `pipelines/pdf_text.py`, `pipelines/pdf.py` `_coverage` | AH-2-shaped hole on the non-OCR path. |
| ingest_file persist `_mark_failed` + folder cycle guard (INGEST-L2/L3) | `tasks/handlers/ingest_file.py` | Small handler hardening; add status-transition unit tests. |

Do not put “split pdf.py” in the same child as AM-1/AM-2/INGEST-H1.

---

## 7. Five-angle conclusions

| Angle | Conclusion |
|---|---|
| **Correctness** | OCR partial-failure (AH-2) is still correctly distinguished (`None` vs `""`, `ocr_failed_pages`, `indexed_partial`). Remaining correctness holes: PDF/text native chunked index fails the whole file on one LLM blip (INGEST-H1); text-layer page extract errors look like blank pages (INGEST-M4); image/archive sampled or failed indexes still look complete (INGEST-M3, INGEST-M5). Handler status machine is sound for pipeline exceptions; persist-phase errors rely on dead-task reconciliation (INGEST-L3). |
| **Security** | Archive member listing/read filters zip-slip and bomb size. Git metadata parse will follow `..` in a crafted `HEAD` ref (INGEST-M1) — local file disclosure into `description`. No SQL, no SSRF in these pipelines. Agent regex is local-tool, not an open HTTP injector. |
| **Architecture** | Pipelines are mostly pure; exception is `ArchivePipeline._resolve_archive_filename` opening a DB session (INGEST-L1). Shared `_text_indexer` is the right degrade path; PDF and text duplicated chunking without it. `pdf.py` remains oversized (INGEST-L4 / A-1). AM-1 import-time constant fights the live `get_settings()` overlay model. AM-2 re-parse is an avoidable resource tax; render handles themselves are closed. Spreadsheet ingest is bounded; read is not (INGEST-M2). |
| **Spec / contract** | `ingest_status=done` plus `coverage.indexed_partial` is the documented partial-failure contract and the backend metadata slice can express it for PDF/office/text/log. Archive and failed image index do not implement that contract. `list_members` on `Pipeline` is unused by `ArchivePipeline` (agent uses `analyze_container`). `OCR_MAX_PAGES` is env-only and frozen at import (AM-1), which contradicts “settings runtime vs import-time”. |
| **Tests** | OCR AH-2, cap, retry, and coverage whitelist are well tested. Handler transitions, chunk-degrade, live OCR cap, git path, archive coverage, image partial, and spreadsheet read bounds are not. One collected skip: `test_rar_e2e` without a `rar` CLI. |

---

## Verification

```
git status --short
# product paths clean. Untracked: .trellis/tasks/08-31-* review dirs, package-lock.json.
# No modified files under src/ or tests/.

uv run pytest tests/ -k "ingest or pdf or office or pipeline or email or archive or markitdown" --collect-only
# 111 selected / 546 deselected / 1 skipped (test_rar_e2e module-level)
```
