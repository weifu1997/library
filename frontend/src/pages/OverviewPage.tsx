import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Folder as FolderIcon,
  Tags as TagsIcon,
  Activity,
  RefreshCw,
  Loader2,
  Inbox,
  Database,
  BrainCircuit,
} from "lucide-react";

import { stats } from "@/api/client";
import type { IngestStatus, StatsOverview } from "@/types/api";
import { useI18n, type I18nStrings } from "@/lib/i18n";

/** A single stat card: big number + label + optional hint line. */
function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof FileText;
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-border/80 bg-bg-card p-5 shadow-xs">
      <div className="flex items-center gap-2 text-[11px] font-semibold text-fg-muted">
        <Icon size={14} className="text-accent shrink-0" />
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-2.5 text-3xl font-bold tracking-tight text-fg-base tabular-nums">
        {value.toLocaleString()}
      </div>
      {hint && (
        <div className="mt-1.5 truncate text-[11px] text-fg-subtle">{hint}</div>
      )}
    </div>
  );
}

function formatRelative(iso: string, t: I18nStrings, localeTag: string): string {
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return "";
  const diffSec = (Date.now() - timestamp) / 1000;
  if (diffSec < 60) return t.time.justNow;
  if (diffSec < 3600) return t.time.minutesAgo(Math.floor(diffSec / 60));
  if (diffSec < 86400) return t.time.hoursAgo(Math.floor(diffSec / 3600));
  if (diffSec < 86400 * 7) return t.time.daysAgo(Math.floor(diffSec / 86400));
  return new Date(iso).toLocaleDateString(localeTag);
}

const INGEST_BADGE: Record<
  IngestStatus,
  { labelKey: "ingestDone" | "ingestFailed" | "ingestPending" | "ingestProcessing"; cls: string }
> = {
  done: { labelKey: "ingestDone", cls: "bg-success-subtle text-success" },
  failed: { labelKey: "ingestFailed", cls: "bg-danger-subtle text-danger" },
  pending: { labelKey: "ingestPending", cls: "bg-warning-subtle text-warning" },
  processing: { labelKey: "ingestProcessing", cls: "bg-info-subtle text-info" },
};

export function OverviewPage() {
  const [data, setData] = useState<StatsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t, localeTag } = useI18n();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await stats.overview();
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const semanticBadge = data
    ? (() => {
        const s = data.semantic;
        if (!s.enabled) {
          return { label: t.overview.semanticDisabled, cls: "bg-bg-muted text-fg-muted" };
        }
        if (s.index_ready) {
          return { label: t.overview.semanticReady, cls: "bg-success-subtle text-success" };
        }
        return {
          label: s.configured
            ? t.overview.semanticNeedsRebuild
            : t.overview.semanticNotBuilt,
          cls: "bg-warning-subtle text-warning",
        };
      })()
    : null;

  const empty = data !== null && data.totals.entries === 0;

  return (
    <div className="flex h-full flex-col select-none bg-bg-base">
      {/* Header */}
      <div className="border-b border-border/80 bg-bg-subtle/80 px-6 py-5 backdrop-blur-md">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20">
              <LayoutDashboard size={18} />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-fg-base">{t.overview.title}</h1>
              <p className="truncate text-[11px] text-fg-subtle">{t.overview.subtitle}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border/80 bg-bg-card px-3 text-xs font-semibold text-fg-muted shadow-xs hover:border-accent/50 hover:text-accent active:scale-95 transition-all disabled:opacity-60"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            {t.overview.refresh}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-4xl space-y-6 animate-fade-in">
          {/* Loading */}
          {loading && !error && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <Loader2 size={22} className="animate-spin text-accent" />
              <p className="mt-3 text-xs text-fg-muted">{t.common.loading}</p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-danger-subtle text-danger border border-danger/30 shadow-xs">
                <RefreshCw size={24} strokeWidth={2} />
              </div>
              <p className="text-sm font-bold text-fg-base">{t.overview.loadError}</p>
              <p className="mt-1.5 max-w-sm break-all text-xs text-fg-muted">{error}</p>
              <button
                type="button"
                onClick={() => void load()}
                className="mt-5 inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-base shadow-xs hover:border-accent/50 hover:text-accent active:scale-95 transition-all"
              >
                <RefreshCw size={13} />
                {t.overview.retry}
              </button>
            </div>
          )}

          {/* Empty library */}
          {!loading && !error && empty && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-card text-accent border border-border/80 shadow-xs">
                <Inbox size={24} strokeWidth={1.8} />
              </div>
              <p className="text-sm font-bold text-fg-base">{t.overview.emptyTitle}</p>
              <p className="mt-1.5 max-w-sm text-xs text-fg-muted leading-relaxed">
                {t.overview.emptyBody}
              </p>
              <Link
                to="/library"
                className="mt-5 inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/80 bg-bg-card px-4 text-xs font-semibold text-accent shadow-xs hover:border-accent/50 hover:bg-bg-subtle active:scale-95 transition-all"
              >
                <FileText size={13} />
                {t.nav.library}
              </Link>
            </div>
          )}

          {/* Content */}
          {!loading && !error && data && !empty && (
            <>
              {/* Stat cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard icon={FileText} label={t.overview.entries} value={data.totals.entries} />
                <StatCard icon={FolderIcon} label={t.overview.folders} value={data.totals.folders} />
                <StatCard icon={TagsIcon} label={t.overview.tags} value={data.totals.tags} />
                <StatCard
                  icon={Activity}
                  label={t.overview.tasks}
                  value={data.tasks.running + data.tasks.pending}
                  hint={t.overview.tasksTotal(data.tasks.running, data.tasks.pending)}
                />
              </div>

              {/* Recent ingest list */}
              <section className="rounded-2xl border border-border/80 bg-bg-card shadow-xs">
                <div className="border-b border-border/60 px-5 py-3.5">
                  <h2 className="text-xs font-bold text-fg-base">{t.overview.recentTitle}</h2>
                </div>
                {data.recent.length === 0 ? (
                  <div className="px-5 py-8 text-center text-xs text-fg-muted">
                    {t.overview.recentEmpty}
                  </div>
                ) : (
                  <ul className="divide-y divide-border/60">
                    {data.recent.map((r) => {
                      const badge = r.ingest_status
                        ? INGEST_BADGE[r.ingest_status]
                        : null;
                      return (
                        <li key={r.entry_id} className="group flex items-center gap-3 px-5 py-3">
                          <Link
                            to={`/library?entry=${encodeURIComponent(r.entry_id)}`}
                            className="flex min-w-0 flex-1 items-center gap-3"
                          >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent border border-accent/20">
                              <FileText size={14} />
                            </div>
                            <div className="min-w-0">
                              <div className="truncate text-[13px] font-semibold text-fg-base group-hover:text-accent transition-colors">
                                {r.display_name}
                              </div>
                              {r.folder_path && (
                                <div className="mt-0.5 flex items-center gap-1 text-[11px] font-mono text-fg-subtle">
                                  <FolderIcon size={11} className="shrink-0" />
                                  <span className="truncate">{r.folder_path}</span>
                                </div>
                              )}
                            </div>
                          </Link>
                          <div className="flex shrink-0 items-center gap-3">
                            {r.created_at && (
                              <span className="hidden text-[11px] text-fg-subtle sm:inline">
                                {formatRelative(r.created_at, t, localeTag)}
                              </span>
                            )}
                            {badge && (
                              <span
                                className={`inline-flex h-5 items-center rounded-full px-2 text-[11px] font-semibold ${badge.cls}`}
                              >
                                {t.overview[badge.labelKey]}
                              </span>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>

              {/* Storage + semantic */}
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-border/80 bg-bg-card p-5 shadow-xs">
                  <div className="flex items-center gap-2 text-[11px] font-semibold text-fg-muted">
                    <Database size={14} className="text-accent shrink-0" />
                    <span>{t.overview.storage}</span>
                  </div>
                  <div className="mt-2 inline-flex h-6 items-center rounded-full bg-bg-muted px-2.5 text-xs font-mono font-semibold text-fg-base">
                    {data.storage_backend}
                  </div>
                </div>
                <div className="rounded-2xl border border-border/80 bg-bg-card p-5 shadow-xs">
                  <div className="flex items-center gap-2 text-[11px] font-semibold text-fg-muted">
                    <BrainCircuit size={14} className="text-accent shrink-0" />
                    <span>{t.overview.semanticTitle}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {semanticBadge && (
                      <span
                        className={`inline-flex h-6 items-center rounded-full px-2.5 text-[11px] font-semibold ${semanticBadge.cls}`}
                      >
                        {semanticBadge.label}
                      </span>
                    )}
                    <span className="text-[11px] text-fg-subtle">
                      {data.semantic.configured
                        ? t.overview.semanticConfigured
                        : t.overview.semanticNotConfigured}
                    </span>
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
