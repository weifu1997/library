/** Right-side metadata drawer for the selected entry.
 *  Collapsed by default to reserve real-estate for the viewer.
 */
import { ChevronRight, ChevronLeft, Tag, Sparkles, FileText, Folder, Layers, ArrowRight, FileWarning } from "lucide-react";
import { Link } from "react-router-dom";

import type { FileMetadata, IngestCoverage } from "@/types/api";
import { cn, formatBytes } from "@/lib/utils";
import { useI18n, type I18nStrings } from "@/lib/i18n";

interface Props {
  meta: FileMetadata | null;
  error?: string | null;
  loading: boolean;
  open: boolean;
  onToggle: () => void;
  onRetry?: () => void;
}

export function MetaPanel({ meta, error, loading, open, onToggle, onRetry }: Props) {
  const { t } = useI18n();
  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-l border-border/80 bg-bg-subtle/70 select-none transition-all duration-200 ease-out",
        open ? "w-80" : "w-9",
      )}
    >
      <button
        onClick={onToggle}
        title={open ? t.library.detailsHide : t.library.detailsShow}
        className="flex h-9.5 items-center justify-center border-b border-border/70 text-fg-subtle hover:bg-bg-muted hover:text-fg-base transition-colors"
        type="button"
      >
        {open ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
      </button>

      {open && (
        <div className="flex-1 overflow-y-auto p-4 text-xs space-y-4">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-8 text-fg-subtle">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent"></span>
              <span>{t.common.loading}</span>
            </div>
          )}
          {!loading && error && (
            <div className="space-y-2 py-6 text-center">
              <p className="text-danger">{t.library.metadataError}</p>
              <p className="break-words text-fg-subtle">{error}</p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="rounded-lg border border-border/80 px-2.5 py-1 text-[11px] font-medium text-fg-base hover:bg-bg-muted"
                >
                  {t.library.metadataRetry}
                </button>
              )}
            </div>
          )}
          {!loading && !error && !meta && (
            <p className="py-8 text-center text-fg-subtle">{t.library.metadataEmpty}</p>
          )}
          {meta && <MetaBody meta={meta} t={t} />}
        </div>
      )}
    </aside>
  );
}

function MetaBody({ meta, t }: { meta: FileMetadata; t: I18nStrings }) {
  return (
    <div className="space-y-4 animate-fade-in">
      {/* File Info Card */}
      <div className="rounded-xl border border-border/80 bg-bg-card p-3.5 shadow-subtle space-y-2.5">
        <Field label={t.library.fields.name} value={meta.display_name} bold />
        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-border/50">
          <Field label={t.library.fields.lifecycle} value={meta.lifecycle} badge />
          {typeof meta.size_bytes === "number" && (
            <Field label={t.library.fields.size} value={formatBytes(meta.size_bytes)} mono />
          )}
        </div>
        {meta.mime_type && <Field label={t.library.fields.mime} value={meta.mime_type} mono />}
        {meta.folder_path && (
          <div className="pt-1 border-t border-border/50 flex items-center gap-1.5 text-fg-muted font-mono text-[10.5px] truncate">
            <Folder size={11} className="text-fg-subtle shrink-0" />
            <span className="truncate">{meta.folder_path}</span>
          </div>
        )}
      </div>

      {/* Partial-index notice — read this before trusting the summary below */}
      <CoverageNotice coverage={meta.coverage} t={t} />

      {/* AI Summary Card */}
      {meta.summary && (
        <section className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-3.5 shadow-subtle">
          <SectionHeader icon={<Sparkles size={12} className="text-accent" />} text={t.library.fields.summary} />
          <p className="mt-2 whitespace-pre-wrap leading-relaxed text-fg-base/90 text-[12.5px] selectable">
            {meta.summary}
          </p>
        </section>
      )}

      {/* Extra Details */}
      {meta.extra && (
        <section className="rounded-xl border border-border/80 bg-bg-card p-3.5 shadow-subtle">
          <SectionHeader icon={<FileText size={12} className="text-fg-subtle" />} text={t.library.fields.extra} />
          <p className="mt-2 whitespace-pre-wrap leading-relaxed text-fg-muted text-[11.5px] selectable">
            {meta.extra}
          </p>
        </section>
      )}

      {/* Tags Cloud */}
      {meta.tags && meta.tags.length > 0 && (
        <section className="rounded-xl border border-border/80 bg-bg-card p-3.5 shadow-subtle">
          <SectionHeader icon={<Tag size={12} className="text-fg-subtle" />} text={t.library.fields.tags} />
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {meta.tags.map((tag) => (
              <span
                key={tag.name}
                className="inline-flex items-center gap-1 rounded-md border border-border/80 bg-bg-subtle px-2 py-0.75 text-[11px] font-medium text-fg-muted hover:border-accent/50 hover:text-fg-base transition-colors"
              >
                {tag.facet ? <span className="text-accent text-[10px]">{tag.facet}:</span> : null}
                <span>{tag.name}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Related Entries */}
      {meta.related_entries && meta.related_entries.length > 0 && (
        <section className="rounded-xl border border-border/80 bg-bg-card p-3.5 shadow-subtle">
          <SectionHeader icon={<Layers size={12} className="text-fg-subtle" />} text={t.library.fields.related} />
          <ul className="mt-2 space-y-1.5">
            {meta.related_entries.slice(0, 8).map((r) => (
              <li key={r.entry_id}>
                <Link
                  to={`/library?entry=${r.entry_id}`}
                  className="group flex items-center justify-between rounded-lg px-2 py-1.5 text-fg-muted hover:bg-bg-muted hover:text-fg-base transition-colors"
                >
                  <span className="truncate text-xs font-medium">{r.display_name}</span>
                  <ArrowRight size={11} className="shrink-0 text-fg-subtle opacity-0 group-hover:opacity-100 transition-opacity" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  bold,
  badge,
}: {
  label: string;
  value: string;
  mono?: boolean;
  bold?: boolean;
  badge?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">{label}</div>
      {badge ? (
        <span className="mt-1 inline-flex items-center rounded-md bg-accent-subtle px-2 py-0.5 text-[10.5px] font-medium text-accent">
          {value}
        </span>
      ) : (
        <div
          className={cn(
            "mt-0.5 break-words text-xs text-fg-base",
            bold && "font-semibold text-sm",
            mono && "font-mono text-[11px] text-fg-muted",
          )}
        >
          {value}
        </div>
      )}
    </div>
  );
}

/** Shown only when the file was NOT indexed in full.
 *
 *  Amber, not red: a partial index is a normal degradation (a page cap was
 *  hit, a few OCR calls failed) and the ingest itself succeeded — red is
 *  reserved for actual ingest failure. The point is that a document missing
 *  pages must not look identical to a complete one, which is exactly what
 *  happened while this data had no outlet at all. */
function CoverageNotice({
  coverage,
  t,
}: {
  coverage?: IngestCoverage | null;
  t: I18nStrings;
}) {
  if (!coverage?.indexed_partial) return null;

  const { total_pages, indexed_pages, ocr_failed_pages } = coverage;
  const showPages =
    typeof total_pages === "number" &&
    typeof indexed_pages === "number" &&
    total_pages > 0;
  // `partial_reasons` is an open vocabulary; an unknown key still renders,
  // carrying the raw key so it stays searchable in a support conversation.
  const reasons = (coverage.partial_reasons ?? []).map(
    (key) => t.library.coverage.reasons[key] ?? t.library.coverage.unknownReason(key),
  );

  return (
    <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3.5 shadow-subtle">
      <SectionHeader
        icon={<FileWarning size={12} className="text-amber-500" />}
        text={t.library.coverage.title}
      />
      {showPages && (
        <p className="mt-2 text-[12px] font-medium text-fg-base/90">
          {t.library.coverage.pages(indexed_pages, total_pages)}
        </p>
      )}
      {typeof ocr_failed_pages === "number" && ocr_failed_pages > 0 && (
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-fg-muted">
          {t.library.coverage.ocrFailed(ocr_failed_pages)}
        </p>
      )}
      {reasons.length > 0 && (
        <ul className="mt-2 space-y-1">
          {reasons.map((reason, i) => (
            <li key={i} className="text-[11.5px] leading-relaxed text-fg-muted">
              · {reason}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SectionHeader({ icon, text }: { icon?: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider text-fg-subtle">
      {icon}
      <span>{text}</span>
    </div>
  );
}
