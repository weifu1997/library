/** Renders one user/agent turn — query, intermediate steps (planning,
 *  thinking, tool calls), final answer, and any error.
 */
import { useEffect, useRef, useState } from "react";
import {
  Brain,
  ChevronDown,
  ListChecks,
  Wrench,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  User as UserIcon,
  Sparkles,
  Clock,
  Zap,
  Maximize2,
  X,
  Code2,
  BarChart3,
  Download,
  FileSpreadsheet,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getBaseUrl, maybeAuthDownload } from "@/api/client";
import { MarkdownView } from "@/components/MarkdownView";
import type { EntryLocator } from "@/components/MarkdownView";
import { useAuthObjectUrl } from "@/components/library/viewers/ViewerShared";
import type { ChatImage, UserArtifact } from "@/types/api";
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
  images?: ChatImage[];
  attachmentUrls?: string[];
  steps: Step[];
  artifacts?: UserArtifact[];
  answer: string | null;
  metrics?: TurnMetrics;
  error: string | null;
  done: boolean;
}

const _IMAGE_MARKER_RE = /\s*\[(?:image|\d+\s+images?)\s+attached\]\s*$/i;

export function TurnView({ turn }: { turn: Turn }) {
  const [open, setOpen] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t } = useI18n();

  const displayQuery = turn.attachmentUrls?.length
    ? turn.query.replace(_IMAGE_MARKER_RE, "")
    : turn.query;

  const inFlight = !turn.done && !turn.error;
  const showSteps = turn.steps.length > 0;
  const hasPlan = turn.steps.some((s) => s.kind === "plan");

  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (hasPlan && !autoOpenedRef.current) {
      autoOpenedRef.current = true;
      setOpen(true);
    }
  }, [hasPlan]);

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
    <div className="space-y-4 text-sm animate-fade-in select-none">
      {/* User Message Bubble */}
      <div className="flex justify-end gap-3 pl-12">
        <div className="flex flex-col items-end max-w-[85%]">
          <div className="rounded-2xl rounded-tr-sm bg-gradient-to-br from-indigo-600 to-indigo-700 px-4.5 py-3 text-white shadow-md shadow-indigo-500/10 selectable">
            <p className="whitespace-pre-wrap leading-relaxed text-[13.5px] font-normal">{displayQuery}</p>
          </div>

          {/* User Attachments Gallery */}
          {turn.images && turn.images.length > 0 && (
            <div className="mt-2 flex flex-wrap justify-end gap-2">
              {turn.images.map((img, i) => {
                const src = `data:${img.media_type};base64,${img.data_b64}`;
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setLightbox(src)}
                    className="group relative h-20 w-20 overflow-hidden rounded-xl border border-border/80 bg-bg-card shadow-sm hover:ring-2 hover:ring-accent transition-all"
                  >
                    <img src={src} alt={`Image ${i + 1}`} className="h-full w-full object-cover" />
                    <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Maximize2 size={14} className="text-white" />
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {turn.attachmentUrls && turn.attachmentUrls.length > 0 && (
            <div className="mt-2 flex flex-wrap justify-end gap-2">
              {turn.attachmentUrls.map((url, i) => (
                <ReplayedImageThumbnail key={i} url={url} onExpand={(src) => setLightbox(src)} />
              ))}
            </div>
          )}
        </div>

        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-bg-muted text-fg-muted shadow-subtle border border-border/60">
          <UserIcon size={15} />
        </div>
      </div>

      {/* Assistant Turn Container */}
      <div className="flex gap-3 pr-12">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-500/20 ring-1 ring-white/20">
          <Sparkles size={15} strokeWidth={2.2} />
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          {/* Steps & Tools Accordion */}
          {showSteps && (
            <div className="rounded-xl border border-border/80 bg-bg-card shadow-subtle overflow-hidden">
              <button
                onClick={() => setOpen((o) => !o)}
                className="flex w-full items-center justify-between px-3.5 py-2 text-xs font-medium text-fg-muted hover:bg-bg-muted/50 transition-colors"
                type="button"
              >
                <div className="flex items-center gap-2">
                  {inFlight && <Loader2 size={13} className="animate-spin text-accent" />}
                  <span className="font-semibold text-fg-base">
                    {inFlight ? t.chat.inProgress : t.chat.steps(turn.steps.length)}
                  </span>
                  <span className="rounded-full bg-bg-muted px-2 py-0.5 font-mono text-[10.5px] text-fg-subtle">
                    {turn.steps.filter((s) => s.kind === "tool_call").length} {t.chat.tool}
                  </span>
                </div>
                <ChevronDown
                  size={14}
                  className={cn("transition-transform duration-200", open && "rotate-180")}
                />
              </button>

              {open && (
                <div className="border-t border-border/60 bg-bg-subtle/50 px-3.5 py-2.5">
                  <ol className="space-y-2">
                    {turn.steps.map((step, idx) => (
                      <StepRow key={idx} step={step} />
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}

          {turn.artifacts && turn.artifacts.length > 0 && (
            <div className="space-y-3">
              {turn.artifacts.map((artifact, idx) => (
                <ArtifactCard
                  key={artifactKey(artifact, idx)}
                  artifact={artifact}
                  conversationId={turn.conversationId}
                />
              ))}
            </div>
          )}

          {/* Answer Markdown Body */}
          {turn.answer && (
            <div className="rounded-2xl border border-border/80 bg-bg-card px-5 py-4 shadow-card selectable">
              <MarkdownView content={turn.answer} onEntryLink={onEntryLink} />
              {turn.metrics && <MetricsLine m={turn.metrics} />}
            </div>
          )}

          {/* Inline Error Banner */}
          {turn.error && (
            <div className="rounded-xl border border-danger/30 bg-danger-subtle/80 p-3.5 text-xs text-danger shadow-sm flex items-start gap-2.5">
              <AlertCircle size={15} className="mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1 font-medium">{turn.error}</div>
            </div>
          )}

          {/* In-Flight Thinking Spinner */}
          {inFlight && !turn.answer && (
            <div className="flex items-center gap-2 text-xs font-medium text-fg-subtle px-1">
              <Loader2 size={13} className="animate-spin text-accent" />
              <span>{t.chat.thinking}</span>
            </div>
          )}
        </div>
      </div>

      {/* Lightbox Modal */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm animate-fade-in"
          onClick={() => setLightbox(null)}
        >
          <div className="relative max-h-[90vh] max-w-[90vw] overflow-hidden rounded-2xl bg-bg-elevated shadow-modal border border-white/10" onClick={(e) => e.stopPropagation()}>
            <img src={lightbox} alt="Enlarged" className="max-h-[85vh] max-w-[85vw] object-contain" />
            <button
              type="button"
              onClick={() => setLightbox(null)}
              className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur hover:bg-black/80 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function artifactKey(artifact: UserArtifact, idx: number): string {
  switch (artifact.kind) {
    case "vega_lite":
      return `vega:${artifact.chart_id}:${idx}`;
    case "data_export":
      return `csv:${artifact.filename}:${idx}`;
    default:
      return `artifact:${idx}`;
  }
}

function ArtifactCard({
  artifact,
  conversationId,
}: {
  artifact: UserArtifact;
  conversationId?: string;
}) {
  const { t } = useI18n();
  switch (artifact.kind) {
    case "vega_lite":
      return <VegaArtifact artifact={artifact} />;
    case "data_export":
      return <CsvArtifact artifact={artifact} conversationId={conversationId} />;
    default:
      return (
        <div className="rounded-xl border border-border/80 bg-bg-card px-4 py-3 text-xs text-fg-muted shadow-subtle">
          {t.chat.unknownArtifact}
        </div>
      );
  }
}

function VegaArtifact({
  artifact,
}: {
  artifact: Extract<UserArtifact, { kind: "vega_lite" }>;
}) {
  const { t } = useI18n();
  const hostRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hostRef.current) return;
    let cancelled = false;
    let view: { finalize: () => void } | null = null;
    setFailed(false);
    setLoading(true);
    void (async () => {
      try {
        const mod = await import("vega-embed");
        if (cancelled || !hostRef.current) return;
        const result = await mod.default(
          hostRef.current,
          artifact.spec as Parameters<typeof mod.default>[1],
          { actions: false, renderer: "canvas" },
        );
        if (cancelled) {
          result.finalize();
          return;
        }
        view = result;
        setLoading(false);
      } catch {
        if (!cancelled) {
          setFailed(true);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      view?.finalize();
    };
  }, [artifact.spec]);

  const onDownloadSpec = () => {
    const blob = new Blob([JSON.stringify(artifact.spec, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${artifact.chart_id}.vl.json`;
    document.body.appendChild(a);
    a.click();
    window.setTimeout(() => {
      a.remove();
      URL.revokeObjectURL(url);
    }, 60_000);
  };

  return (
    <div className="rounded-xl border border-border/80 bg-bg-card p-3.5 shadow-subtle">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex items-start gap-2">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
            <BarChart3 size={13} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-fg-base">
              {artifact.title || t.chat.chart}
            </div>
            {artifact.caption && (
              <p className="mt-0.5 text-xs text-fg-muted">{artifact.caption}</p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onDownloadSpec}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-border/50 px-2 py-1 text-[11px] font-medium text-fg-muted hover:bg-bg-muted hover:text-fg-base"
        >
          <Download size={11} />
          {t.chat.downloadSpec}
        </button>
      </div>
      {failed ? (
        <div className="rounded-md bg-bg-muted/80 px-3 py-2 text-xs text-fg-muted">
          {t.chat.chartRenderFailed}
          {artifact.caption && (
            <p className="mt-1 text-fg-subtle">{artifact.caption}</p>
          )}
        </div>
      ) : (
        <div className="relative w-full overflow-x-auto">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center text-fg-subtle">
              <Loader2 size={14} className="animate-spin" />
            </div>
          )}
          <div ref={hostRef} className="w-full min-h-[320px]" />
        </div>
      )}
    </div>
  );
}

function CsvArtifact({
  artifact,
  conversationId,
}: {
  artifact: Extract<UserArtifact, { kind: "data_export" }>;
  conversationId?: string;
}) {
  const { t } = useI18n();
  const href = conversationId
    ? `${getBaseUrl()}/v1/conversations/${encodeURIComponent(conversationId)}/exports/${encodeURIComponent(artifact.filename)}`
    : undefined;

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border/80 bg-bg-card px-3.5 py-3 shadow-subtle">
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-muted text-fg-muted">
          <FileSpreadsheet size={15} />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-fg-base">
            {artifact.filename}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-fg-subtle">
            <span>{t.chat.exportCsv}</span>
            <span>·</span>
            <span>{t.chat.exportRows(artifact.row_count)}</span>
            {artifact.truncated && (
              <>
                <span>·</span>
                <span className="font-medium text-warning">{t.chat.truncated}</span>
              </>
            )}
          </div>
        </div>
      </div>
      {href && (
        <a
          href={href}
          download={artifact.filename}
          onClick={(e) => maybeAuthDownload(e, href, artifact.filename)}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-border/50 bg-bg-muted/60 px-2.5 py-1.5 text-[11px] font-medium text-fg-base hover:bg-bg-muted"
        >
          <Download size={12} />
          {t.chat.downloadCsv}
        </a>
      )}
    </div>
  );
}

function ReplayedImageThumbnail({
  url,
  onExpand,
}: {
  url: string;
  onExpand: (src: string) => void;
}) {
  const { src: blobUrl, err } = useAuthObjectUrl(url);

  if (!blobUrl && !err) {
    return (
      <div className="flex h-20 w-20 items-center justify-center rounded-xl border border-border bg-bg-card">
        <Loader2 size={14} className="animate-spin text-fg-subtle" />
      </div>
    );
  }
  if (err || !blobUrl) return null;

  return (
    <button
      type="button"
      onClick={() => onExpand(blobUrl)}
      className="group relative h-20 w-20 overflow-hidden rounded-xl border border-border bg-bg-card shadow-sm hover:ring-2 hover:ring-accent transition-all"
    >
      <img src={blobUrl} alt="Attachment" className="h-full w-full object-cover" />
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity">
        <Maximize2 size={14} className="text-white" />
      </div>
    </button>
  );
}

function StepRow({ step }: { step: Step }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const liveDurationMs = useLiveStepDurationMs(step);
  const durationMs = step.durationMs ?? liveDurationMs;
  const Icon = ICONS[step.kind] ?? Wrench;

  const hasArgs = step.args && Object.keys(step.args).length > 0;
  const hasPreview = Boolean(step.resultPreview);
  const expandable = hasArgs || hasPreview || Boolean(step.plan && step.plan.length > 0);

  return (
    <li className="rounded-lg border border-border/50 bg-bg-card/70 p-2.5 text-xs transition-colors">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-bg-muted text-fg-muted">
            <Icon size={13} />
          </div>
          <span className="truncate font-medium text-fg-base">{step.label}</span>
        </div>

        {/* Step Status Badge */}
        <div className="flex items-center gap-2 shrink-0">
          {durationMs != null && (
            <span className="flex items-center gap-1 font-mono text-[10.5px] text-fg-subtle">
              <Clock size={11} />
              {shortDuration(durationMs / 1000)}
            </span>
          )}

          {step.kind === "tool_call" && (
            <span>
              {step.result === "ok" ? (
                <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10.5px] font-medium text-emerald-500">
                  <CheckCircle2 size={11} /> ok
                </span>
              ) : step.result === "failed" ? (
                <span className="flex items-center gap-1 rounded bg-danger-subtle px-1.5 py-0.5 text-[10.5px] font-medium text-danger">
                  <XCircle size={11} /> failed
                </span>
              ) : (
                <span className="flex items-center gap-1 rounded bg-accent-subtle px-1.5 py-0.5 text-[10.5px] font-medium text-accent">
                  <Loader2 size={11} className="animate-spin" /> running
                </span>
              )}
            </span>
          )}

          {expandable && (
            <button
              onClick={() => setDetailOpen((o) => !o)}
              className="flex h-6.5 w-6.5 items-center justify-center rounded-lg text-fg-subtle hover:bg-bg-card hover:text-fg-base active:scale-95 transition-all shadow-xs border border-border/40"
              type="button"
            >
              <Code2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Plan Details */}
      {step.plan && step.plan.length > 0 && (
        <ol className="mt-2 space-y-1 rounded-md bg-bg-subtle p-2">
          {step.plan.map((p, i) => (
            <li key={i} className="flex items-start gap-2 text-[11.5px] text-fg-muted">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-[9.5px] font-bold text-accent">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 leading-snug">{p}</span>
            </li>
          ))}
        </ol>
      )}

      {/* Code / Args Expansion */}
      {detailOpen && (
        <div className="mt-2 space-y-1.5 font-mono text-[10.5px]">
          {hasPreview && (
            <div>
              <div className="text-[10px] uppercase font-semibold text-fg-subtle">Preview</div>
              <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap rounded bg-bg-muted p-2 text-fg-base">
                {step.resultPreview}
              </pre>
            </div>
          )}
          {hasArgs && (
            <div>
              <div className="text-[10px] uppercase font-semibold text-fg-subtle">Arguments</div>
              <pre className="mt-0.5 overflow-x-auto rounded bg-bg-muted p-2 text-fg-base">
                {prettyArgs(step.args!, step.entryNames, step.tagNames)}
              </pre>
            </div>
          )}
        </div>
      )}

      {step.error && (
        <div className="mt-2 rounded bg-danger-subtle px-2 py-1 text-[11px] text-danger border border-danger/20 font-mono">
          {step.error}
        </div>
      )}
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
  const parts: { label: string; icon?: React.ReactNode }[] = [];
  if (m.duration_ms != null) parts.push({ label: shortDuration(m.duration_ms / 1000), icon: <Clock size={11} /> });
  if (m.tokens_in != null || m.tokens_out != null) {
    parts.push({ label: t.chat.tokens(fmtTokens(m.tokens_in ?? 0), fmtTokens(m.tokens_out ?? 0)), icon: <Zap size={11} /> });
  }
  const promptTokens = m.prompt_tokens ?? m.tokens_in;
  if (m.cache_read && promptTokens) {
    const pct = Math.round((m.cache_read / promptTokens) * 100);
    parts.push({ label: t.activity.cache(pct) });
  }
  if (m.tool_calls != null) parts.push({ label: t.chat.tools(m.tool_calls) });

  if (parts.length === 0) return null;

  return (
    <div className="mt-3.5 flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-3 text-[11px] text-fg-subtle">
      {parts.map((p, i) => (
        <span key={i} className="inline-flex items-center gap-1 rounded-md bg-bg-muted/80 px-2 py-0.5 font-mono">
          {p.icon}
          {p.label}
        </span>
      ))}
      {m.truncated && (
        <span className="inline-flex items-center gap-1 rounded-md bg-warning-subtle px-2 py-0.5 font-mono text-warning font-semibold">
          ⚠ {t.chat.truncated}
        </span>
      )}
    </div>
  );
}

function fmtTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

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
