# Library

> Chinese README: [README.zh-CN.md](README.zh-CN.md)
> Detailed design: [DESIGN.md](DESIGN.md)
> GUI setup guide: [English](docs/GUI_TUTORIAL.md) · [中文](docs/GUI_TUTORIAL.zh-CN.md)

**Turn your PDFs, notes, spreadsheets, logs, and archives into a private AI
library that answers from original sources.**

Library is a local-first research agent for people with messy private
knowledge bases. It keeps your files in a normal folder tree, builds useful
library metadata around them, and makes the agent read the relevant original
file windows before it writes a cited answer.

[GUI setup guide](docs/GUI_TUTORIAL.md) · [CLI quickstart](#cli-quickstart) · [Usage guide](USAGE.md) ·
[Design notes](DESIGN.md)

![Library promotional hero](docs/images/library-promo-en.png)

## Why Use It

- You have research papers, meeting notes, PDFs, tables, logs, screenshots, and
  archives that do not fit cleanly into one app.
- You want answers that cite the source material instead of a black-box vector
  search layer over chunks.
- You need both quick lookups and slower investigation-style reports over the
  same private library.
- You want local-first storage: the default `mirror` backend keeps your library
  as readable files under `LIBRARY_HOME/library`.

## What It Does

- Ingests text, Markdown, PDFs, DOCX, images, spreadsheets, logs, and archives.
- Organizes material with folders, catalogs, tags, views, metadata, journals,
  and relation mining.
- Recalls candidates with lexical search by default, plus optional embeddings,
  `sqlite-vec`, reranking, and source quotas.
- Reads original sections, pages, lines, archive members, or table slices before
  answering.
- Produces cited answers and reports, then writes durable investigation notes
  that future turns can recall.

## Try It

### Web GUI

The browser GUI lives in `frontend/`. In development, start the backend
first, then the Vite dev server:

```bash
library serve            # backend (task runner runs in-process by default)
cd frontend
npm install
npm run dev              # open http://localhost:5173
```

Point the GUI at a remote backend by setting the API base URL in the
Settings page, or keep the default (Vite proxies `/v1` and `/health` to
`http://127.0.0.1:8000`).

### CLI Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
library init
```

Edit `.env`:

```ini
LIBRARY_API_HOST=127.0.0.1
LIBRARY_API_PORT=8000
LLM_DEFAULT_PROVIDER=openai
LLM_DEFAULT_API_KEY=sk-...
LLM_DEFAULT_MODEL=gpt-4o-mini
```

Run the embedded CLI + API + worker:

```bash
library
```

Then:

```text
library> /upload ./paper.pdf /papers/
library> /background
library> compare this paper with my Paxos notes
library> /export
```

The first launch bootstraps the database schema automatically. Managed
deployments can instead run `library-db-prepare` before rollout and set
`RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=false` for both API and worker replicas.

To share one backend across the web GUI, CLI sessions, MCP, skill-driven
automation, or external HTTP clients, start the reusable HTTP backend instead:

```bash
library serve
```

`library serve` reads `LIBRARY_API_HOST` and `LIBRARY_API_PORT` from
`.env` and writes its live URL to `LIBRARY_HOME/runtime/server.json`.
The web GUI and CLI clients auto-discover that file; skills inherit this when they
drive the `library` CLI. Explicit `--server URL` or `LIBRARY_SERVER`
still take precedence.

## Example Questions

```text
Compare this Raft paper with my Paxos notes.
Find the incident timeline across the logs and the postmortem.
Which uploaded papers support this claim, and which contradict it?
Summarize the spreadsheet, then cite the rows used for the conclusion.
Turn this folder into a cited research brief.
```

## How It Differs From Plain RAG

Library is not just "retrieve top-k chunks and answer." The agent can recall
prior investigations, inspect structured metadata, follow related entries, read
original source windows, and correct its search path before writing. Quick mode
keeps this bounded for short lookups; Deep mode keeps the full ReAct
investigation loop when coverage matters more than latency.

## The Retrieval Funnel

```text
user question
  -> plan
  -> recall_knowledge            # journal + metadata + optional semantic recall
  -> search_metadata/list_folder # focused follow-up over names, summaries, tags
  -> read_entries_metadata       # sections, extra, related entries
  -> discover/related entries    # graph-based neighbours
  -> read_files                  # original text/page/line/member/table slice
  -> answer with footnotes
  -> reflect_turn                # durable journal memory
```

The agent is instructed to use `recall_knowledge` for broad material location.
That tool resolves tag hints, searches prior journal notes and entry metadata,
optionally adds semantic candidates, ranks the merged pool, and returns compact
candidate IDs for batched metadata verification and source reads. Lower-level
tools such as `search_journal`, `search_metadata`, and `materialize_view`
remain available for focused follow-up and debugging.

Metadata text search is indexed in both supported database modes. SQLite uses
the local FTS5 trigram table; Postgres uses native `to_tsvector` /
`websearch_to_tsquery` expression GIN indexes over file and entry metadata.
Chinese short terms that are too small for trigram tokenization are preserved
with a bounded LIKE fallback in mixed metadata queries.
Journal recall also validates referenced entries at read time. If a prior
note points at a deleted entry or a file reprocessed after the note was
written, the note is kept for audit but marked stale and ranked behind current
notes. Later reflections can also mark directly contradicted journal rows
`invalidated_*`; active recall hides them by default while audit queries can
include them.

## Supported Ingest Pipelines

- `text`: text, Markdown, reStructuredText, code-like text.
- `pdf`: text-layer PDF, long-PDF page windows, PDF page labels, scanned-PDF OCR fallback when a vision profile is configured.
- `image`: image indexing and description when a vision profile is configured.
- `docx`: Word documents.
- `spreadsheet`: CSV, TSV, JSON, XLSX, Parquet and related table formats.
- `log`: logs and logrotate variants.
- `archive`: zip, tar, 7z, rar, gz, bz2, xz, iso, cab and other py7zz-supported containers.

## Retrieval Evaluation

External retrieval datasets can be imported from a local BEIR-style directory:

```text
<dataset>/
  corpus.jsonl
  queries.jsonl
  qrels/test.tsv
```

Import is synchronous. Each corpus document is written as a normal entry and
immediately passed through the ingest pipeline, so the command returns only
after the eval corpus is indexed.

```bash
LIBRARY_HOME=./runtime/eval/scifact library eval import-beir scifact ./datasets/scifact
LIBRARY_HOME=./runtime/eval/scifact EMBEDDING_API_KEY=... library eval build-semantic-index scifact
LIBRARY_HOME=./runtime/eval/scifact library eval run scifact --retriever search_metadata --k 10,50,100 --json report.json
LIBRARY_HOME=./runtime/eval/scifact library eval run scifact --retriever semantic_recall --k 10,50,100
LIBRARY_HOME=./runtime/eval/scifact library eval ablation-run scifact --k 10,50,100 --json ablation-report.json
LIBRARY_HOME=./runtime/eval/scifact library eval load-run scifact --retriever recall_knowledge --requests 1000 --concurrency 20 --max-p95-ms 1500 --min-hit-at-k 0.90 --json load-report.json
LIBRARY_HOME=./runtime/eval/scifact library eval answer scifact --retriever recall_knowledge --query-id <qid> --timeout-seconds 300
LIBRARY_HOME=./runtime/eval/scifact library eval answer-run scifact --retriever recall_knowledge --qrels-only --query-limit 20 --concurrency 10 --json answer-report.json
LIBRARY_HOME=./runtime/eval/scifact library eval compare-report scifact --query-limit 30 --concurrency 3 --json compare-report.json
```

Use a dedicated `LIBRARY_HOME` for external benchmarks unless you
intentionally want benchmark documents inside your personal library.
`eval build-semantic-index` uses the configured embedding provider. The
default is Alibaba Cloud Model Studio / DashScope `text-embedding-v4`; set
`EMBEDDING_API_KEY` before building. Embedding credentials are intentionally
separate from `LLM_*` profiles. Semantic recall is optional and disabled by
default; set `SEMANTIC_RECALL_ENABLED=true` to merge semantic candidates from
the default semantic index with the lexical metadata recall path. The eval CLI
index builder targets imported datasets; the GUI/API can enqueue a whole-library
semantic-index rebuild for the default index after embedding model or dimension
changes. Ingest also refreshes the affected file's semantic vectors after a
successful run when semantic recall is configured. If the optional `sqlite-vec`
dependency is installed, the semantic index also writes `vectors.sqlite` and
search uses it before falling back to the file index. Install with
`pip install -e ".[semantic]"`, or set `SEMANTIC_INDEX_BACKEND=file` to keep
only the file backend.
Whole-library rebuilds read database rows in bounded pages controlled by
`SEMANTIC_REBUILD_PAGE_SIZE`. Lexical candidates without a section locator can
receive the best scoped semantic section when its cosine score reaches
`SECTION_BACKFILL_MIN_SCORE`, improving rerank evidence and citation precision
without adding unrelated candidates.
Content-addressed duplicate uploads never revive soft-deleted file rows. A
duplicate of failed or incomplete content resumes ingest; a duplicate of ready
content schedules a file-scoped semantic refresh. That refresh reuses an
existing vector only when its provider, model, dimensions, and section text
hash match the current embedding configuration.
Optional reranking can refine the merged candidate pool before evidence
selection. Enable it with `RERANK_ENABLED=true`, `RERANK_API_KEY=...`, and
optionally `RERANK_MODEL=qwen3-rerank`. Rerank credentials are also separate
from `LLM_*`; no chat or vision key is reused implicitly. Evidence selection
defaults to `EVIDENCE_SELECTION=quota`; set `EVIDENCE_SELECTION=rerank` to take
the reranked top evidence directly.

Each LLM profile can explicitly declare its request dialect, context window,
tokenizer, image/tool/temperature support, and accepted output-token parameter.
The settings UI exposes these fields and the runtime does not guess a gateway
dialect from its URL. Oversized conversation requests are compacted by model
tokens into a structured checkpoint while stored turns remain unchanged;
`CONVERSATION_COMPACTION_*` controls this separately from evidence compression.
Session metrics also classify prompt-cache SLO status as `met`, `breached`, or
`insufficient_data` using the configurable `AGENT_CACHE_SLO_*` thresholds.
The eval report treats `hit@k` and `candidate_recall@k` as the investigation
candidate-pool metrics; MRR and nDCG are ranking-efficiency diagnostics.
`eval ablation-run` runs the candidate-pool matrix for metadata-only,
metadata-plus-relations, hybrid semantic recall, hybrid-plus-relations,
hybrid-plus-rerank, and full recall. It reports deltas against metadata-only
so relation expansion, semantic recall, and rerank contributions can be
tracked before changing the agent loop.
`eval load-run` runs bounded concurrent retrieval requests and reports request
rate, error rate, p50/p95/p99 latency, Hit@K, and MRR. Optional thresholds make
the command return a non-zero exit code for repeatable scale gates.
`eval answer` is a bounded final-answer probe: it retrieves candidates, reads
limited source text, performs one answer-generation call, and reports whether
the answer cited a qrels-relevant document. `eval answer-run` repeats the same
bounded probe across imported queries and reports aggregate final-answer
citation hit rate; use `--qrels-only` to apply `--query-limit` after filtering
to imported qrels-backed queries and `--concurrency` to run independent answer
probes in parallel. When BEIR query metadata includes SciFact-style
SUPPORT/CONTRADICT labels, the answer report also includes label accuracy.
`eval compare-report` runs a blind end-to-end comparison between a one-shot
RAG report and the full ReAct investigation workflow on the same query set.
When SciFact-style gold labels are available, the judge prioritizes verdict
correctness before report completeness.

Latest local validation on SciFact 300:

- Retrieval with `recall_knowledge` + rerank top-80 reached MRR 0.7226,
  hit@10 0.8800, and hit@100 0.9133.
- Bounded final-answer probes with rerank top-80 and quota evidence selection
  reached evidence hit 0.8667, citation hit 0.7133, and label accuracy 0.8085.
- A 30-query end-to-end report comparison favored the full ReAct workflow over
  one-shot RAG in 26/30 cases, with 2 one-shot RAG wins, 2 ties, and 1 timeout.

These results support Library's current positioning: for quick lookups it
behaves like a hybrid RAG system, while the full ReAct workflow is a slower
deep-investigation path that can produce better source-grounded reports.
They should not be read as a claim of general benchmark SOTA: the dataset is
small, the comparison target is a local one-shot RAG baseline, and final
quality still depends on model behavior, ingest quality, and available
evidence.

## CLI Surface

`library` with no arguments opens the interactive REPL. The same command
surface is also available as one-shot subcommands for scripts, CI, and agents
that do not use MCP:

```bash
library ask "Compare this Raft paper with my Paxos notes"
library search "raft consensus" --json
library info <entry_id> --json
library discover <entry_id> --top-k 12 --json
library check --json
library ingest --all --yes --json
library reprocess failed --json
```

One-shot commands use the same backend discovery model as the REPL: explicit
`--server URL`, then `LIBRARY_SERVER`, then
`LIBRARY_HOME/runtime/server.json`, and finally an embedded backend. Text
output is meant for humans; `--json` keeps stdout structured for automation.

Slash commands:

```text
/help                         list commands
/upload <local> <remote>      upload a file or directory into the vault
/check                        diff mirror vault vs database
/ingest <path> | --all        sync manual vault edits into the database
/reprocess failed             re-run ingest for failed files
/reprocess folder <id> failed re-run failed files in one folder subtree
/search <query>               metadata recall
/info <entry_id>              entry metadata and preview
/discover <entry_id> [N]      related entries from the evidence graph
/discover <entry_id> --all    include unvetted relation signals
/discover <entry_id> --vet    queue background vetting for direct signals
/tree                         folder tree
/download <id> [dest]         download file or folder zip
/export [conversation_id]     export answer and citations
/tend                         run a maintenance pass
/background                   show queued/running tasks
/mode [auto|quick|deep]       show or change chat mode
/new / /clear / /quit         session control
```

Any non-slash input is sent to the investigator agent. Chat defaults to
`auto`: the planner selects a quick/standard/deep execution budget from a
plain `BUDGET:` control line and the runtime can upgrade it while tools are
still producing new evidence. `/mode quick` and `/mode deep` remain manual
overrides.

## MCP Server

Library can also run as a stdio MCP server for external agents:

```bash
library mcp
# or
library-mcp
```

The MCP server uses the same backend discovery model as the CLI: explicit
`--server URL`, then `LIBRARY_SERVER`, then
`LIBRARY_HOME/runtime/server.json`, and finally an embedded backend if
nothing is already running. A Claude Desktop-style command entry can point at
the same executable and set `LIBRARY_HOME` / database settings through the
environment.

MCP exposes structured workflow tools including `ask_library`,
`upload_file`, `download_file`, `download_folder`, `export_conversation`,
`search_files`, `get_file_metadata`, plus retrieval/source-reading tools such
as `recall_knowledge`, `search_metadata`, `search_journal`,
`read_entries_metadata`, and `read_files`.

## API Surface

Business endpoints live under `/v1`:

```text
POST /v1/upload
GET  /v1/search
GET  /v1/file-entries/{entry_id}/metadata
GET  /v1/file-entries/{entry_id}/content
POST /v1/sessions
POST /v1/chat/{session_id}          # Server-Sent Events
GET  /v1/conversations/{id}/events  # resume after an SSE cursor
POST /v1/conversations/{id}/cancel
GET  /v1/conversations/{id}/export
POST /v1/tend
GET  /v1/tasks/active
GET  /v1/settings/llm
GET  /health
GET  /live
GET  /ready
```

The web GUI and CLI both use the same API.

`POST /v1/chat/{session_id}` accepts `{ "query": "...", "mode": "deep" }`
or `{ "query": "...", "mode": "quick" }`. Omit `mode` for the default `auto`
planner-selected budget behavior.

## Configuration

Core `.env` fields:

```ini
LIBRARY_HOME=~/LibraryData
DB_BACKEND=sqlite                  # sqlite or postgres
RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=true # false after managed Alembic migration
STORAGE_BACKEND=mirror             # mirror, local, or s3
WORKER_ENABLED=true
WORKER_SCHEDULER_ENABLED=true       # false: normal tasks only, no periodic fan-out
WORKER_RETRY_BASE_SECONDS=60
WORKER_RETRY_MAX_SECONDS=3600
LIBRARY_UPLOAD_MAX_BYTES=0      # per-file upload cap; 0 = unlimited
LIBRARY_DOCUMENT_LIMIT=0           # optional global gates; 0 = disabled
LIBRARY_STORAGE_BYTES_LIMIT=0
INGEST_BACKLOG_LIMIT=0
CHAT_CONCURRENCY_LIMIT=0
AUTO_LIFECYCLE_ENABLED=false
MAINTENANCE_DAILY_TOKEN_BUDGET=0  # rolling 24h background cap; 0 = unlimited
RELATION_BACKGROUND_VETTING_ENABLED=false

LLM_DEFAULT_PROVIDER=openai        # openai, openai-compatible, anthropic
LLM_DEFAULT_API_KEY=sk-...
LLM_DEFAULT_BASE_URL=
LLM_DEFAULT_MODEL=gpt-4o-mini

LLM_CHAT_MODEL=
LLM_REFLECT_MODEL=
LLM_INGEST_MODEL=
LLM_VISION_MODEL=

EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
SEMANTIC_RECALL_ENABLED=false
SEMANTIC_INDEX_BACKEND=auto        # auto, file, sqlite-vec
SECTION_EMBEDDING_MAX_SECTIONS=200 # 0 keeps document-level vectors only

RERANK_ENABLED=false
RERANK_API_KEY=
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-api/v1
RERANK_MODEL=qwen3-rerank
EVIDENCE_SELECTION=quota           # quota or rerank

AGENT_PLAN_MAX_TOKENS=2048
AGENT_EXECUTE_MAX_TOKENS=4096
AGENT_MAX_PARALLEL_TOOL_CALLS=8
AGENT_FINAL_ANSWER_CONTINUE_TURNS=3
AGENT_FINAL_ANSWER_MAX_CHARS=120000

LLM_INGEST_MAX_TOKENS=1200
LLM_INGEST_CONCURRENCY=4
LLM_VISION_SUPPORTS_VISION=true

# Built-in compression.
COMPRESSION_ENABLED=true
COMPRESSION_MIN_CHARS=12000
COMPRESSION_TARGET_CHARS=8000
COMPRESSION_CONTEXT_CHARS=220
COMPRESSION_MAX_RATIO=0.85
```

Use `openai-compatible` for DeepSeek, Together, Groq, local vLLM, Ollama, and other OpenAI wire-compatible services.

The `vision` profile is optional. Without it, image enrichment, PDF figure captioning, and scanned-PDF OCR degrade gracefully or are skipped.

Compression uses one master switch, `COMPRESSION_ENABLED`. Library vendors the dependency-free Headroom SearchCompressor, LogCompressor, SmartCrusher, and TextCrusher cores for large `read_files` model views, model-facing results from `search_metadata`, `query_sql`, and `query_log`, structured/log ingest views, archive member peeks, and long aggregate index prompts. It fails open to original content if a compressed view does not beat `COMPRESSION_MAX_RATIO`. Persisted tool-call results, UI previews, and original files stay unmodified; compressed `read_files` metadata includes `compress=false` reopen args for exact quoting.

`MAINTENANCE_DAILY_TOKEN_BUDGET` is a rolling 24-hour cap for background
maintenance LLM usage. When it is exhausted, low-priority speculative tasks
(`restructure_catalogs`, `vet_relations`, `propose_views`) defer to a later
tick; foreground ingest and chat reflection are not limited.

Relation discovery is pure-read by default. Miners write cheap raw signals,
and `/discover` reads the already-vetted graph without calling an LLM. Use
`/discover <entry_id> --vet` (API: `vet=true`) to queue background vetting for
that seed's direct raw edges, or set `RELATION_BACKGROUND_VETTING_ENABLED=true`
if you want the periodic worker to batch-vet relation edges ahead of time.

When a long final answer hits the model token limit, Library can continue it server-side and emit one merged answer event to the GUI. Tune `AGENT_FINAL_ANSWER_CONTINUE_TURNS` and `AGENT_FINAL_ANSWER_MAX_CHARS` for research-heavy deployments.

Chat events are committed to a per-conversation ledger before delivery. SSE
frames carry monotonic `id` cursors; the web GUI and CLI clients reconnect from
the last cursor, and `GET /v1/conversations/{id}/events` also accepts
`Last-Event-ID`. Disconnecting a viewer does not cancel the turn. Explicit
cancel requests stop the background task and persist a terminal error event.

### Reliability and recovery

Each claimed task receives a unique delivery-owner token. Heartbeats,
completion, retries, and expired-lease recovery must still match that owner
and the expected lease, so a stalled worker cannot complete or retry work after
another worker has reclaimed it. Losing ownership also cancels the old local
handler. Retry delays grow exponentially between
`WORKER_RETRY_BASE_SECONDS` and `WORKER_RETRY_MAX_SECONDS`; periodic dispatcher
ticks use time-slot keys so the running tick cannot consume its successor.
Set `WORKER_SCHEDULER_ENABLED=false` on queue-only workers: they continue
claiming ordinary tasks but neither seed nor execute `periodic_tick`.
Retention pruning deletes audit rows, terminal task delivery records, task
outcomes, and durable chat events in bounded batches. During schema bootstrap,
legacy duplicate active dedup keys are collapsed to
the best executable task before the uniqueness constraint is installed.

`LIBRARY_UPLOAD_MAX_BYTES` is checked while multipart data is streaming,
before Starlette spools the file. File bytes are counted independently from a
bounded amount of form metadata. Upload commit ambiguity triggers compensating
cleanup, local `.part` files are removed, failed S3 multipart uploads are
aborted, and physical object deletion is represented by a persistent retryable
task. PostgreSQL deployments also use transaction advisory locks for
conflicting tool scopes, concurrent turns, and capacity check-and-create
windows. Transaction-pooled PostgreSQL proxies should set
`POSTGRES_PREPARED_STATEMENT_CACHE_SIZE=0`; asyncpg then uses unique prepared
statement names. `/live` checks only the process, while `/ready` concurrently
checks database and storage with `READINESS_TIMEOUT_SECONDS` and returns 503
when either dependency is unavailable. Local installs leave
`RUNTIME_SCHEMA_BOOTSTRAP_ENABLED=true`; managed deployments can run
`library-db-prepare` once and set it to false so API and worker replicas do
not run startup DDL concurrently.

Features that require a different multi-tenant data model remain out of scope:
organizations and users, ACL/RLS isolation, shared-library slugs, and an
external job-queue database. Library keeps single-library ownership and
polls its own `tasks` table, while durable chat delivery stays within that
model.

## Storage and Deployment

Default local layout:

```text
<LIBRARY_HOME>/library.db
<LIBRARY_HOME>/library/
<LIBRARY_HOME>/objects/
```

`STORAGE_BACKEND=mirror` stores files as a readable folder tree. `local` stores UUID-addressed objects. `s3` is for multi-host deployments.

Single-process mode:

```bash
library
```

Remote API mode:

```bash
library serve --host 0.0.0.0 --port 8000
library --server http://server:8000
# If the server sets LIBRARY_API_TOKEN:
library --server http://server:8000 --api-token "$LIBRARY_API_TOKEN"
```

Docker compose starts API, worker, Postgres, and MinIO:

```bash
echo "LLM_DEFAULT_API_KEY=sk-..." > .env
docker compose up -d
```

Compose runs the one-shot database preparation service first, then starts API
and worker with runtime schema bootstrap disabled.

The compose file binds the API and MinIO console to `127.0.0.1` by default.
If you deliberately expose the API on a LAN, set `LIBRARY_API_TOKEN` and
send `Authorization: Bearer <token>` from the CLI or web GUI connection
settings.

### Multi-device sync

Do not use Dropbox, Syncthing, iCloud Drive, OneDrive, or similar file-sync
tools to sync a live `LIBRARY_HOME`. SQLite and the mirror/local storage
layout can be corrupted by concurrent replication. For multiple machines, use
the remote deployment shape with Postgres and S3-compatible object storage.

## Documentation

- [USAGE.md](USAGE.md): operations manual.
- [DESIGN.md](DESIGN.md): data model, retrieval design, task system, invariants.
- [samples/architecture.md](samples/architecture.md): developer architecture overview.
- [docs/LAUNCH.md](docs/LAUNCH.md): launch copy, social preview notes, and community post templates.

## Development

```bash
uv run ruff check src tests
.\.venv\Scripts\python -B -m pytest tests -q
```

Current tests cover upload, ingest, agent runtime, tool execution, export, task scheduling, PDF/DOCX/image/table/archive pipelines, relation discovery, lifecycle behavior, semantic index fallback, recall/rerank scoring, evaluation commands, and CLI flows.

## Community links
This open-source project is linked with and recognized by the LINUX DO community:

LINUX DO: [https://linux.do/](https://linux.do/)

Thanks to [Headroom](https://github.com/chopratejas/headroom) for the compression algorithms and architecture vendored into Library's built-in compression path.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
