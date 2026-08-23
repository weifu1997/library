/** Renders one user/agent turn — query, intermediate steps (planning,
 *  thinking, tool calls), final answer, and any error.
 *
 *  Mirrors cli/commands.py:chat: tool calls render as
 *  `calling search_metadata(q="...")`, the answer block carries the
 *  agent's own `[^a]: entry_id=… - reason` footnote definitions which
 *  remark-gfm v4 turns into a proper footnote section, and the trailer
 *  shows `(1m 54s · ↑ 2.9k / ↓ 2.9k tokens · 87% cache · 2 tools)`.
 */
import { useEffect, useRef, useState } from "react";
import {
  Brain, ChevronDown, ListChecks, Wrench, CheckCircle2, XCircle,
  AlertCircle, Loader2, User as UserIcon,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { MarkdownView } from "@/components/MarkdownView";
import type { EntryLocator } from "@/components/MarkdownView";
import { useAuthObjectUrl } from "@/components/library/viewers/ViewerShared";
import type { ChatImage } from "@/types/api";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export type StepKind = "planning" | "plan" | "thinking" | "tool_call";

export interface Step {
  kind: StepKind;
  label: string;
  toolName?: string;
  toolCallId?: string;
  args?: Record<string, unknown>;
  entryNames?: Record<string, string>;
  tagNames?: Record<string, string>;
  plan?: string[];
  result?: "ok" | "failed";
  resultPreview?: string;
  startedAtMs?: number;
  durationMs?: number;
  error?: string;
}

export interface TurnMetrics {
  tokens_in?: number;
  prompt_tokens?: number;
  tokens_out?: number;
  cache_read?: number;
  cache_creation?: number;
  cache_eligible_prompt_tokens?: number;
  cache_eligible_read_tokens?: number;
  cache_eligible_estimated_tokens?: number;
  cache_eligible_requests?: number;
  cache_eligible_hit_ratio?: number | null;
  cache_eligible_reuse_ratio?: number | null;
  prompt_prefix_breaks?: number;
  cache_slo?: {
    status: "met" | "breached" | "insufficient_data";
    minimum_hit_ratio: number;
    minimum_eligible_requests: number;
  };
  tool_calls?: number;
  llm_calls?: number;
  duration_ms?: number;
  truncated?: boolean;
}

export interface Turn {
  query: string;
  conversationId?: string;
  /** Images attached to this user turn. Present only on live turns that
   *  were sent with attachments; historical/replayed turns omit them since
   *  their bytes ride on the SSE request, not the transcript. */
  images?: ChatImage[];
  /** Fully-qualified attachment URLs for a replayed turn, one per stored
   *  image (see ReplayedTurn.attachments). Present only on transcript
   *  turns; live turns carry raw base64 in `images` instead. Loaded through
   *  the authenticated-blob mechanism so a token-protected backend still
   *  serves them. UI-only re-display — never re-sent to the LLM. */
  attachmentUrls?: string[];
  steps: Step[];
  answer: string | null;
  metrics?: TurnMetrics;
  error: string | null;
  done: boolean;
}

// The persisted user_message carries a "[image attached]" / "[N images
// attached]" placeholder so the LLM history knows an image was present, but
// once the thumbnails re-display we strip that marker from the shown text.
const _IMAGE_MARKER_RE = /\s*\[(?:image|\d+\s+images?)\s+attached\]\s*$/i;

export function TurnView({ turn }: { turn: Turn }) {
  const [open, setOpen] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t } = useI18n();

  // Hide the "[image attached]" placeholder on replayed image turns (the
  // thumbnail below now shows the image); keep raw text on live/text turns.
  const displayQuery = turn.attachmentUrls?.length
    ? turn.query.replace(_IMAGE_MARKER_RE, "")
    : turn.query;

  const inFlight = !turn.done && !turn.error;
  const showSteps = turn.steps.length > 0;
  const hasPlan = turn.steps.some((s) => s.kind === "plan");

  // Auto-open the steps drawer the first time a plan step lands —
  // surfacing the plan is the whole point of expanding it. Don't keep
  // re-opening it after the user closes it manually.
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (hasPlan && !autoOpenedRef.current) {
      autoOpenedRef.current = true;
      setOpen(true);
    }
  }, [hasPlan]);

  // `entry:<uuid>` links in citation footnotes resolve to a Library
  // deep-link. Hand them to react-router so the tree expands to that
  // file in-app instead of the browser trying to open a custom-scheme
  // URL. When the citation carries a position locator (runtime.py
  // rewrites footnote defs into one or more query fields), preserve all of
  // them so Office links can navigate and highlight in one click.
  const onEntryLink = (id: string, locator?: EntryLocator) => {
    const q = new URLSearchParams({ entry: id });
    if (locator?.quote) q.set("q", locator.quote);
    if (locator?.line) q.set("line", locator.line);
    if (locator?.page) q.set("page", locator.page);
    if (locator?.block) q.set("block", locator.block);
    if (locator?.sheet) q.set("sheet", locator.sheet);
    if (locator?.cell) q.set("cell", locator.cell);
    if (locator?.row) q.set("row", locator.row);
    navigate(`/library?${q.toString()}`);
  };

  return (
    <div className="mb-6 animate-fade-in">
      <div className="mb-2 flex items-start gap-2">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-bg-muted text-fg-muted">
          <UserIcon size={13} />
        </div>
        {displayQuery.length > 0 && (
          <div className="whitespace-pre-wrap text-sm">{displayQuery}</div>
        )}
      </div>

      {((turn.images && turn.images.length > 0)
        || (turn.attachmentUrls && turn.attachmentUrls.length > 0)) && (
        <div className="ml-8 mb-2 flex flex-wrap gap-2">
          {turn.images?.map((img, i) => {
            const src = `data:${img.media_type};base64,${img.data_b64}`;
            return (
              <img
                key={`live-${i}`}
                src={src}
                alt={t.chat.imageAlt(i + 1)}
                onClick={() => setLightbox(src)}
                className="h-16 w-16 cursor-zoom-in rounded-md border border-border object-cover"
              />
            );
          })}
          {turn.attachmentUrls?.map((url, i) => (
            <ReplayedAttachment
              key={`replay-${i}`} url={url} index={i} onOpen={setLightbox}
            />
          ))}
        </div>
      )}

      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 cursor-zoom-out animate-fade-in"
        >
          <img
            src={lightbox}
            alt={t.chat.imageAlt(1)}
            onClick={(e) => e.stopPropagation()}
            className="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
          />
        </div>
      )}

      {showSteps && (
        <div className="ml-8 mb-2">
          <button
            onClick={() => setOpen((o) => !o)}
            className="group flex items-center gap-1.5 text-xs text-fg-muted hover:text-fg-base"
          >
            <ChevronDown
              size={12}
              className={cn("transition-transform", !open && "-rotate-90")}
            />
            <span>
              {t.chat.steps(turn.steps.length)}
              {inFlight && ` · ${t.chat.inProgress}`}
            </span>
            {inFlight && <Loader2 size={11} className="animate-spin" />}
          </button>
          {open && (
            <ul className="mt-2 space-y-1.5 border-l border-border pl-3 text-xs">
              {turn.steps.map((s, i) => (
                <StepRow key={i} step={s} />
              ))}
            </ul>
          )}
        </div>
      )}

      {turn.answer !== null && turn.answer.length > 0 && (
        <div className="ml-8 rounded-lg border border-border bg-bg-subtle p-4 text-sm">
          <MarkdownView
            content={turn.answer}
            onEntryLink={onEntryLink}
            idPrefix={turn.conversationId
              ? `user-content-${turn.conversationId}-`
              : undefined}
          />
          {turn.metrics && <MetricsLine m={turn.metrics} />}
        </div>
      )}

      {turn.error && (
        <div className="ml-8 mt-2 flex items-start gap-2 rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span className="break-all">{turn.error}</span>
        </div>
      )}

      {inFlight && turn.answer === null && !showSteps && (
        <div className="ml-8 flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 size={13} className="animate-spin" /> {t.chat.waiting}
        </div>
      )}
    </div>
  );
}

/** A single replayed image thumbnail. Loads the stored attachment through
 *  the shared authenticated-blob hook so a token-protected backend still
 *  serves it (object URL revoked on unmount by the hook). Keeps a fixed-size
 *  box so the loading/error states don't shift layout, matching the live
 *  pasted-image thumbnails. */
function ReplayedAttachment(
  { url, index, onOpen }:
  { url: string; index: number; onOpen: (src: string) => void },
) {
  const { t } = useI18n();
  const { src, err } = useAuthObjectUrl(url);
  if (src) {
    return (
      <img
        src={src}
        alt={t.chat.imageAlt(index + 1)}
        onClick={() => onOpen(src)}
        className="h-16 w-16 cursor-zoom-in rounded-md border border-border object-cover"
      />
    );
  }
  return (
    <div
      className="flex h-16 w-16 items-center justify-center rounded-md border border-border bg-bg-muted text-fg-subtle"
      title={err ?? undefined}
    >
      {err
        ? <AlertCircle size={14} />
        : <Loader2 size={14} className="animate-spin" />}
    </div>
  );
}

function StepRow({ step }: { step: Step }) {
  const Icon = ICONS[step.kind];
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const liveDurationMs = useLiveStepDurationMs(step);
  const argsAvailable = step.args && Object.keys(step.args).length > 0;
  // Once a tool result has streamed in, prefer showing it in the expander
  // — args are already encoded in the one-line label, so re-printing them
  // is just noise. Args remain the fallback while the call is in flight.
  const previewAvailable = !!step.resultPreview;
  const expandable = previewAvailable || argsAvailable;
  const expandTitle = previewAvailable
    ? t.chat.expandResult
    : t.chat.expandArgs;
  const isPlan = step.kind === "plan" && step.plan && step.plan.length > 0;
  const durationMs = step.durationMs ?? liveDurationMs;
  return (
    <li className="flex items-start gap-2 text-fg-muted">
      <Icon size={12} className={cn(
        "mt-0.5 shrink-0",
        isPlan ? "text-accent" : "text-fg-subtle",
      )} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {expandable ? (
            <button
              onClick={() => setOpen((o) => !o)}
              className={cn(
                "truncate text-left hover:text-fg-base",
                step.result === "failed" && "text-danger",
              )}
              title={expandTitle}
            >
              {step.label}
            </button>
          ) : (
            <span className={cn(
              "truncate",
              step.result === "failed" && "text-danger",
              isPlan && "font-medium text-fg-base",
            )}>
              {step.label}
            </span>
          )}
          {step.result === "ok" && <CheckCircle2 size={11} className="text-accent" />}
          {step.result === "failed" && <XCircle size={11} className="text-danger" />}
          {durationMs != null && (
            <span className="text-fg-subtle">{shortDuration(durationMs / 1000)}</span>
          )}
        </div>
        {isPlan && (
          <ol className="mt-1.5 space-y-1 rounded-md border border-border bg-bg-base/60 p-2 text-[12px] text-fg-base">
            {step.plan!.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-[10px] font-semibold leading-none text-accent">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1 [&_p]:my-0 [&_p]:leading-snug">
                  <MarkdownView content={p} />
                </div>
              </li>
            ))}
          </ol>
        )}
        {open && previewAvailable && (
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-bg-muted px-2 py-1 font-mono text-[10.5px] text-fg-muted">
{step.resultPreview}
          </pre>
        )}
        {open && !previewAvailable && argsAvailable && (
          <pre className="mt-1 overflow-x-auto rounded bg-bg-muted px-2 py-1 font-mono text-[10.5px] text-fg-muted">
{prettyArgs(step.args!, step.entryNames, step.tagNames)}
          </pre>
        )}
        {step.error && (
          <div className="mt-1 truncate text-[11px] text-danger" title={step.error}>
            {step.error}
          </div>
        )}
      </div>
    </li>
  );
}

function useLiveStepDurationMs(step: Step): number | undefined {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (step.kind !== "thinking" || step.durationMs != null || step.startedAtMs == null) {
      return;
    }
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [step.kind, step.durationMs, step.startedAtMs]);

  if (step.kind !== "thinking" || step.durationMs != null || step.startedAtMs == null) {
    return undefined;
  }
  return Math.max(0, nowMs - step.startedAtMs);
}

function MetricsLine({ m }: { m: TurnMetrics }) {
  const { t } = useI18n();
  const parts: string[] = [];
  if (m.duration_ms != null) parts.push(shortDuration(m.duration_ms / 1000));
  if (m.tokens_in != null || m.tokens_out != null) {
    parts.push(t.chat.tokens(fmtTokens(m.tokens_in ?? 0), fmtTokens(m.tokens_out ?? 0)));
  }
  const promptTokens = m.prompt_tokens ?? m.tokens_in;
  if (m.cache_read && promptTokens) {
    const pct = Math.round((m.cache_read / promptTokens) * 100);
    parts.push(t.activity.cache(pct));
  }
  if (m.cache_slo) parts.push(t.activity.cacheSlo(m.cache_slo.status));
  if (m.tool_calls != null) parts.push(t.chat.tools(m.tool_calls));
  if (parts.length === 0) return null;
  return (
    <div className="mt-3 border-t border-border pt-2 font-mono text-[11px] text-fg-subtle">
      ({parts.join(" · ")}){m.truncated && <span className="ml-2 text-warning">⚠ {t.chat.truncated}</span>}
    </div>
  );
}

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

// Render a tool-call args dict as `key: value` lines, with entry_id values
// replaced by `display_name (01abcdef)` using the resolver maps the server
// sends alongside the tool_call event. Mirrors how kb-lite's tool_display
// surfaces filenames instead of raw uuids; tagNames does the same for
// search_metadata's tags_all/tags_any/tags_none.
function prettyArgs(
  args: Record<string, unknown>,
  entryNames?: Record<string, string>,
  tagNames?: Record<string, string>,
): string {
  const isUuid = (s: string) => /^[0-9a-fA-F-]{32,}$/.test(s);
  const TAG_KEYS = new Set(["tags_all", "tags_any", "tags_none"]);

  const subst = (v: unknown, parentKey?: string): unknown => {
    if (typeof v === "string" && isUuid(v)) {
      if (entryNames?.[v]) return `${entryNames[v]} (${v.slice(0, 8)})`;
      if (tagNames?.[v] && parentKey && TAG_KEYS.has(parentKey))
        return `${tagNames[v]} (${v.slice(0, 8)})`;
    }
    if (Array.isArray(v)) return v.map((x) => subst(x, parentKey));
    if (v && typeof v === "object") {
      const out: Record<string, unknown> = {};
      for (const [k, vv] of Object.entries(v as Record<string, unknown>)) {
        out[k] = subst(vv, k);
      }
      return out;
    }
    return v;
  };

  const lines: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    const sv = subst(v, k);
    if (sv === null || sv === undefined || sv === "") continue;
    if (typeof sv === "string") {
      lines.push(`${k}: ${sv}`);
    } else if (Array.isArray(sv) && sv.every((x) => typeof x === "string")) {
      lines.push(`${k}: ${(sv as string[]).join(", ")}`);
    } else {
      lines.push(`${k}: ${JSON.stringify(sv, null, 2)}`);
    }
  }
  return lines.join("\n");
}

function shortDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

const ICONS = {
  planning: ListChecks,
  plan: ListChecks,
  thinking: Brain,
  tool_call: Wrench,
} as const;
