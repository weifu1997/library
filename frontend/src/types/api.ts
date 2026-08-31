/** Shared types mirroring the /v1/ JSON shapes.
 *
 *  MVP response types are aliases of `openapi-typescript` output from
 *  `openapi/openapi.json`. Non-MVP types stay handwritten. Do not replace
 *  this file wholesale.
 */
import type { components } from "./generated/openapi";
import type {} from "./generated/usage";

export type IngestStatus = "pending" | "processing" | "done" | "failed";

export type FolderIngestSummary = Omit<
  components["schemas"]["FolderIngestSummary"],
  "status"
> & {
  status: IngestStatus | null;
};

export type Folder = Omit<
  components["schemas"]["FolderResponse"],
  "ingest_summary"
> & {
  ingest_summary?: FolderIngestSummary | null;
};

export type FileEntrySummary = Omit<
  components["schemas"]["FileEntrySummary"],
  "ingest_status"
> & {
  ingest_status?: IngestStatus | null;
};

export type FolderListing = {
  folders: Folder[];
  entries: FileEntrySummary[];
};

export type FolderDetail = Folder & {
  children: Folder[];
  entries: FileEntrySummary[];
};

export type UploadResult = components["schemas"]["UploadResponse"];

export type SearchResult = components["schemas"]["SearchResponse"];

export type SearchEntry = components["schemas"]["SearchEntry"];

export interface RelatedEntry {
  entry_id: string;
  display_name: string;
  score: number;
  visit_count?: number;
  direct_edge_weight?: number;
}

export interface FileMetadata {
  entry_id: string;
  display_name: string;
  folder_id: string | null;
  folder_path?: string;
  size_bytes?: number;
  mime_type?: string | null;
  lifecycle: string;
  summary?: string | null;
  tags?: { name: string; facet?: string | null }[];
  extra?: string | null;
  coverage?: IngestCoverage | null;
  related_entries?: RelatedEntry[];
  webdav_remote?: WebDavRemoteMarker | null;
  [key: string]: unknown;
}

/** How completely this file was indexed at ingest time. Absent on records
 *  ingested before coverage tracking, and every field is optional — the
 *  backend drops anything malformed rather than failing the request.
 *
 *  `partial_reasons` is an open vocabulary: the backend adds new reasons
 *  over time (`ocr_page_failures` arrived with the OCR retry work), so the
 *  UI must render unknown keys instead of blanking them. */
export interface IngestCoverage {
  indexed_partial?: boolean;
  partial_reasons?: string[];
  total_pages?: number;
  indexed_pages?: number;
  ocr_used?: boolean;
  ocr_pages_done?: number;
  ocr_failed_pages?: number;
}

export interface WebDavRemoteMarker {
  remote_root?: string;
  library_id?: string;
  snapshot_id?: string;
  blob_path?: string;
  sha256?: string;
  hydrated?: boolean;
  imported_at?: string;
  hydrated_at?: string;
}

/** Folder ancestor chain (root → leaf) for an entry, returned by
 *  GET /v1/file-entries/{id}/path. The Library tree consumes this
 *  to expand each ancestor in turn before selecting the file. */
export interface EntryPath {
  entry_id: string;
  display_name: string;
  folder_id: string | null;
  ancestors: { id: string; name: string }[];
}

export type SessionInfo = components["schemas"]["SessionCreateResponse"] & {
  mode?: ChatMode;
};

export type SessionListEntry = Omit<
  components["schemas"]["SessionListEntry"],
  "mode"
> & {
  mode: ChatMode;
};

export type SessionList = Omit<
  components["schemas"]["SessionListResponse"],
  "sessions" | "next_cursor"
> & {
  sessions: SessionListEntry[];
  next_cursor?: string | null;
};

export interface ReplayedToolCall {
  tool_call_id?: string | null;
  tool_index?: number | null;
  turn?: number | null;
  name: string | null;
  arguments: Record<string, unknown>;
  /** Server-resolved one-line summary, mirrors the live SSE
   *  tool_call event. Names referenced as ids (entry/tag/folder/
   *  catalog) come back resolved so the GUI prints a readable label
   *  instead of a uuid. Optional for forward-compatibility with
   *  older transcripts. */
  display?: string | null;
  ok: boolean;
  error: string | null;
  duration_ms: number | null;
  /** One-line summary of the tool result, mirrors what the live SSE
   *  `tool_result` event carries in its `preview` field. Null when the
   *  call ran but produced no result body (legacy rows). */
  preview?: string | null;
}

export interface ReplayedTurn {
  conversation_id: string;
  turn_index: number;
  mode: ChatMode;
  started_at: string | null;
  ended_at: string | null;
  user_message: string;
  agent_response: string | null;
  error: string | null;
  plan_text: string | null;
  tool_calls: ReplayedToolCall[];
  /** User-visible side-channel payloads recovered from persisted
   *  tool_calls[*].result.__user_only__ (charts, CSV exports). Absent on
   *  legacy transcripts. Never contains the raw tool result or filesystem
   *  paths. */
  artifacts?: UserArtifact[];
  /** Pasted chat images stored for this turn, re-served for UI display
   *  only. Empty (or absent on legacy transcripts) when the turn had no
   *  stored images. These are NEVER re-sent to the LLM — the runtime keeps
   *  only the "[image attached]" text placeholder in conversation history;
   *  saving to disk + serving is decoupled from the LLM message tape. Each
   *  entry loads from
   *  GET /v1/conversations/{conversation_id}/attachments/{name}. */
  attachments?: Array<{ name: string; media_type: string }>;
  metrics: {
    tokens_in: number;
    prompt_tokens: number;
    tokens_out: number;
    cache_read: number;
    cache_creation: number;
    cache_eligible_prompt_tokens: number;
    cache_eligible_read_tokens: number;
    cache_eligible_estimated_tokens: number;
    cache_eligible_requests: number;
    cache_eligible_hit_ratio: number | null;
    cache_prompt_coverage_ratio: number | null;
    cache_eligible_reuse_ratio: number | null;
    prompt_prefix_breaks: number;
    cache_slo: CacheSlo;
    tool_calls: number;
    llm_calls: number;
    duration_ms: number;
  };
}

export interface SessionTranscript {
  session_id: string;
  started_at: string | null;
  ended_at: string | null;
  end_reason: string | null;
  mode: ChatMode;
  metrics: ReplayedTurn["metrics"];
  turns: ReplayedTurn[];
}

export type SessionTotals = components["schemas"]["SessionCloseResponse"];

export type CacheSlo = components["schemas"]["CacheSlo"];

export type RunningCount = components["schemas"]["RunningCountResponse"];

export type ActiveTask = Omit<
  components["schemas"]["ActiveTaskItem"],
  "file_id" | "entry_id"
> & {
  file_id?: string | null;
  entry_id?: string | null;
};

export type ActiveTasks = {
  running: ActiveTask[];
  pending: ActiveTask[];
};

export type RecentTask = Omit<
  components["schemas"]["RecentTaskItem"],
  "file_id" | "entry_id" | "status"
> & {
  file_id?: string | null;
  entry_id?: string | null;
  status: "done" | "dead" | string;
};

export type RecentTasks = {
  items: RecentTask[];
  next_cursor?: string | null;
};

export type OnConflict = "rename" | "error" | "skip";
export type ChatMode = "auto" | "deep" | "quick";

/** A per-turn image attachment carried in the chat POST body. Mirrors the
 *  backend llm ImageBlock (media_type + data_b64). `data_b64` is RAW base64
 *  of the image bytes with NO `data:` URI prefix. Images belong to the
 *  current turn only and are never persisted or re-sent on later turns. */
export interface ChatImage {
  media_type: "image/png" | "image/jpeg" | "image/gif" | "image/webp";
  data_b64: string;
}

/** SSE event names emitted by POST /v1/chat/{session_id}.
 *  Order in a typical turn: conversation → planning → plan → thinking
 *  → (tool_call → tool_result)* → answer → done. `error` may
 *  interrupt at any time. */
export type ChatEventType =
  | "conversation"
  | "planning"
  | "plan"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "user_artifact"
  | "answer"
  | "error"
  | "done"
  | "message";

export interface ChatEvent<T = unknown> {
  type: ChatEventType;
  data: T;
  raw: string;
  eventCursor?: number;
  conversationId?: string;
}

export interface ConversationEventData {
  conversation_id: string;
}

export interface PlanBudgetData {
  mode?: ChatMode;
  tier?: "quick" | "standard" | "deep";
  initial_tier?: "quick" | "standard" | "deep";
  limit?: number;
  hard_limit?: number;
  source?: string;
  upgrades?: number;
}

export interface PlanEventData {
  text?: string;
  budget?: PlanBudgetData;
}

export interface ThinkingEventData {
  round?: number;
  limit?: number;
  final_continuation?: boolean;
  mode?: ChatMode;
  budget_tier?: "quick" | "standard" | "deep";
  budget_initial_tier?: "quick" | "standard" | "deep";
  budget_upgrades?: number;
  budget_upgraded?: boolean;
  previous_limit?: number;
  hard_limit?: number;
  force_final_answer?: boolean;
}

export interface ToolCallEventData {
  name: string;
  arguments: Record<string, unknown>;
  tool_call_id?: string;
}

export interface ToolResultEventData {
  tool_call_id?: string;
  name?: string;
  result?: unknown;
  ok?: boolean;
  duration_ms?: number;
}

/** Vega-Lite chart or CSV export shown to the user, never to the model. */
export type UserArtifact =
  | {
      kind: "vega_lite";
      chart_id: string;
      title?: string;
      caption?: string;
      spec: Record<string, unknown>;
    }
  | {
      kind: "data_export";
      format: "csv";
      filename: string;
      row_count: number;
      truncated?: boolean;
      columns?: string[];
    };

export interface UserArtifactEventData {
  tool_call_id?: string;
  tool_index?: number;
  turn?: number;
  tool?: string;
  payload?: unknown;
}

export interface AnswerEventData {
  text: string;
  citations?: Array<{
    marker: string;
    entry_id: string;
    display_name?: string;
  }>;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    tool_calls?: number;
    llm_calls?: number;
    duration_ms?: number;
  };
}

export interface ApiErrorBody {
  detail?: string | Record<string, unknown>;
}

// ---- stats / overview -----------------------------------------------------

/** One row of the Overview page's "recently ingested" list, mirroring
 *  GET /v1/stats/overview `recent[]`. */
export type StatsRecentEntry = Omit<
  components["schemas"]["StatsRecentEntry"],
  "ingest_status"
> & {
  ingest_status: IngestStatus | null;
};

/** Aggregated read-only snapshot served by GET /v1/stats/overview. */
export type StatsOverview = Omit<
  components["schemas"]["StatsOverviewResponse"],
  "recent"
> & {
  recent: StatsRecentEntry[];
};

// ---- settings -------------------------------------------------------------

export type ServerSettings = Omit<
  components["schemas"]["ServerSettingsResponse"],
  "webdav"
> & {
  webdav?: WebDavStatus;
}

export interface WebDavSyncLast {
  ok?: boolean;
  status?: "running" | "success" | "failed" | string;
  phase?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  snapshot_id?: string | null;
  remote_path?: string | null;
  latest_snapshot?: string | null;
  selected_entries?: number;
  selected_files?: number;
  total_blobs?: number;
  processed_blobs?: number;
  uploaded_blobs?: number;
  skipped_blobs?: number;
  total_metadata_files?: number;
  uploaded_metadata_files?: number;
  entry_count?: number;
  blob_count?: number;
  blob_bytes?: number;
  error?: string | null;
  last_pull_at?: string | null;
  last_pulled_snapshot_id?: string | null;
  last_pull?: Record<string, number>;
  last_download_at?: string | null;
  last_download?: {
    requested_files?: number;
    downloaded_files?: number;
    failed_files?: number;
    errors?: Array<{ entry_id: string; error: string }>;
  };
  last_remote_check_at?: string | null;
  remote_status?: "available" | "empty" | "failed" | string;
  remote_updated_at?: string | null;
  remote_snapshot_id?: string | null;
  remote_latest_snapshot?: string | null;
  remote_app_version?: string | null;
  remote_entry_count?: number | null;
  remote_blob_count?: number | null;
  remote_blob_bytes?: number | null;
  remote_error?: string | null;
}

export interface WebDavStatus {
  configured: boolean;
  url?: string | null;
  username?: string | null;
  password_set: boolean;
  remote_path: string;
  auto_sync_enabled: boolean;
  auto_sync_interval_minutes: number;
  last?: WebDavSyncLast | null;
}

export type WebDavPublishResult = components["schemas"]["WebDavPublishResponse"];

export interface WebDavRemoteStatusResult {
  ok: boolean;
  remote_path: string;
  status: "available" | "empty" | "failed" | string;
  checked_at: string;
  latest?: unknown | null;
  manifest?: unknown | null;
}

export interface WebDavPullResult {
  ok: boolean;
  remote_path: string;
  snapshot_id?: string | null;
  folders: number;
  catalogs: number;
  views: number;
  tags: number;
  tag_aliases: number;
  entries: number;
  entry_tags: number;
  relations: number;
  remote_files: number;
}

export interface WebDavDownloadResult extends WebDavPullResult {
  downloaded_files: number;
  failed_files: number;
  errors: Array<{ entry_id: string; error: string }>;
}

export type WebDavPlanReason = "new" | "changed" | "missing" | "not_hydrated" | string;

export interface WebDavPlanItem {
  entry_id: string;
  display_name: string;
  folder_id?: string | null;
  folder_path?: string | null;
  size_bytes?: number;
  sha256?: string;
  updated_at?: string | null;
  reason: WebDavPlanReason;
}

export interface WebDavPlanResult {
  ok: boolean;
  remote_path: string;
  snapshot_id?: string | null;
  remote_updated_at?: string | null;
  app_version?: string | null;
  count: number;
  items: WebDavPlanItem[];
}

export interface WebDavPublishSelectedResult {
  ok: boolean;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  snapshot_id?: string | null;
  remote_path?: string | null;
  latest_snapshot?: string | null;
  selected_entries?: number;
  selected_files?: number;
  total_blobs?: number;
  processed_blobs?: number;
  uploaded_blobs?: number;
  skipped_blobs?: number;
  total_metadata_files?: number;
  uploaded_metadata_files?: number;
  entry_count?: number;
  blob_count?: number;
  blob_bytes?: number;
  error?: string | null;
}

export interface WebDavHydrateResult {
  ok: boolean;
  entry_id: string;
  file_id: string;
  hydrated: boolean;
  already_local?: boolean;
  storage_key?: string;
}

export type SemanticIndexStatus = components["schemas"]["SemanticIndexStatus"];

export interface SemanticIndexRebuildResult {
  task_id: string | null;
  index_name: string;
  status: SemanticIndexStatus;
}

export type LlmVisibleProfileName = "chat" | "reflect" | "ingest" | "vision";
export type LlmProfileName = "default" | LlmVisibleProfileName;

/** Failover target for a profile. Only the four fields that reach a
 *  different endpoint; capabilities inherit the primary. `api_key` is
 *  always masked by the server (never the raw secret). */
export type LlmBackupProfile = components["schemas"]["LlmBackup"];

export type LlmProfileResolved = components["schemas"]["LlmProfileResolved"];

export type LlmModelCapabilities = components["schemas"]["LlmCapabilities"];

export type LlmSettings = components["schemas"]["LlmSettingsResponse"];
export type LlmSettingsPut = components["schemas"]["LlmSettingsPutResponse"];

/** One model served by a provider's model-listing endpoint. `display_name`
 *  is only populated by Anthropic; OpenAI returns ids only. */
export type LlmModelInfo = components["schemas"]["LlmModelInfo"];

/** Result of POST /v1/settings/llm/models — always 200 with a per-call `ok`
 *  verdict, mirroring the test endpoint. */
export type LlmModelsResult = components["schemas"]["LlmModelsResponse"];

export interface FilePreviewText {
  entry_id: string;
  file_id: string;
  display_name: string;
  pipeline: string;
  text: string;
  total_chars: number;
  returned_chars: number;
  truncated: boolean;
}
