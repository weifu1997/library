import { useEffect, useMemo, useState } from "react";
import { FileText, Download, Cloud, Loader2, FileCode, FileImage, FileSpreadsheet, Book, FileArchive, FileBox } from "lucide-react";

import { fileEntries, maybeAuthDownload, webdavSync } from "@/api/client";
import type { FileMetadata } from "@/types/api";
import { formatBytes } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import {
  ArchiveView,
  BinaryView,
  CodeView,
  EpubView,
  ExtractedMarkdownView,
  ImageView,
  MdView,
  OfficeDocumentView,
  PdfView,
  TextView,
} from "./FileViewerViews";

export interface ViewerLocator {
  quote?: string;
  line?: string;
  page?: string;
  block?: string;
  sheet?: string;
  cell?: string;
  row?: string;
}

interface Props {
  entryId: string;
  meta: FileMetadata | null;
  locator?: ViewerLocator | null;
  onLocatorConsumed?: () => void;
  onHydrated?: () => void;
}

type Kind = "pdf" | "image" | "md" | "text" | "code" | "docx" | "xlsx" | "pptx" | "epub" | "email" | "archive" | "binary";
type OfficeKind = "docx" | "xlsx" | "pptx";

const TEXT_EXT = new Set([
  "txt", "log", "csv", "tsv", "ini", "conf", "env", "sql", "rst",
]);
const CODE_EXT_TO_LANG: Record<string, string> = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  py: "python", rb: "ruby", go: "go", rs: "rust", java: "java",
  c: "c", h: "c", cpp: "cpp", hpp: "cpp",
  json: "json", yaml: "yaml", yml: "yaml", toml: "toml",
  html: "html", css: "css", scss: "scss",
  sh: "bash", bash: "bash", zsh: "bash", ps1: "powershell",
  md: "markdown",
};
const ARCHIVE_EXT = new Set([
  "zip", "tar", "tgz", "gz", "bz2", "xz", "lzma", "7z", "rar", "iso", "cab",
]);

function classifyByName(name: string): Kind {
  const lower = name.toLowerCase();
  const ext = (name.split(".").pop() || "").toLowerCase();
  if (ext === "pdf") return "pdf";
  if (["avif", "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "tif", "tiff", "heic", "heif"].includes(ext)) return "image";
  if (ext === "md" || ext === "markdown") return "md";
  if (ext === "docx") return "docx";
  if (ext === "xlsx" || ext === "xlsm") return "xlsx";
  if (ext === "pptx" || ext === "pptm") return "pptx";
  if (ext === "epub") return "epub";
  if (ext === "eml" || ext === "msg") return "email";
  if (
    ARCHIVE_EXT.has(ext)
    || [".tar.gz", ".tar.bz2", ".tar.xz"].some((suffix) => lower.endsWith(suffix))
  ) return "archive";
  if (CODE_EXT_TO_LANG[ext]) return "code";
  if (TEXT_EXT.has(ext)) return "text";
  return "binary";
}

function isOfficeKind(kind: Kind): kind is OfficeKind {
  return kind === "docx" || kind === "xlsx" || kind === "pptx";
}

function parseLineRange(value: string): { start: number; end: number } | null {
  const m = /^(\d+)(?:-(\d+))?$/.exec(value.trim());
  if (!m) return null;
  const start = parseInt(m[1], 10);
  const end = m[2] ? parseInt(m[2], 10) : start;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1) return null;
  return { start, end: Math.max(start, end) };
}

export function FileViewer({ entryId, meta, locator, onLocatorConsumed, onHydrated }: Props) {
  const { t } = useI18n();
  const [hydrating, setHydrating] = useState(false);
  const [hydrateError, setHydrateError] = useState<string | null>(null);
  const name = meta?.display_name || "";
  const kind = useMemo<Kind>(() => classifyByName(name), [name]);
  const contentUrl = fileEntries.contentUrl(entryId);
  const downloadUrl = fileEntries.downloadUrl(entryId);
  const remote = meta?.webdav_remote;
  const needsHydrate = Boolean(remote && !remote.hydrated);

  const lineLoc = locator?.line ? parseLineRange(locator.line) : null;
  const pageLoc = locator?.page ? parseInt(locator.page, 10) : null;
  const blockLoc = locator?.block ? parseInt(locator.block, 10) : null;
  const rowLoc = locator?.row ? parseInt(locator.row, 10) : null;
  const quoteLoc = locator?.quote || null;

  useEffect(() => {
    if (kind === "pdf" && locator && onLocatorConsumed) onLocatorConsumed();
  }, [kind, locator, onLocatorConsumed]);

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col select-none">
      {/* File Header Bar */}
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border/80 bg-bg-subtle/80 px-4 text-xs backdrop-blur">
        <div className="flex min-w-0 items-center gap-2.5">
          <FileHeaderIcon kind={kind} />
          <span className="truncate font-semibold text-fg-base text-sm">{name || t.common.unset}</span>
          <span className="rounded bg-bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            {kind}
          </span>
          {typeof meta?.size_bytes === "number" && (
            <span className="hidden sm:inline-block font-mono text-[11px] text-fg-subtle">
              {formatBytes(meta.size_bytes)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {needsHydrate ? (
            <button
              type="button"
              disabled={hydrating}
              onClick={async () => {
                setHydrating(true);
                setHydrateError(null);
                try {
                  await webdavSync.hydrate(entryId);
                  onHydrated?.();
                } catch (e) {
                  setHydrateError(e instanceof Error ? e.message : String(e));
                } finally {
                  setHydrating(false);
                }
              }}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border/80 bg-bg-card px-3.5 text-xs font-semibold text-fg-muted hover:bg-bg-subtle hover:text-fg-base disabled:opacity-50 transition-all shadow-xs active:scale-95"
            >
              {hydrating ? <Loader2 size={12} className="animate-spin text-accent" /> : <Cloud size={12} />}
              <span>{t.library.hydrateFromWebDav}</span>
            </button>
          ) : (
            <a
              href={downloadUrl}
              download
              onClick={(e) => maybeAuthDownload(e, downloadUrl, name)}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border/80 bg-bg-card px-3.5 text-xs font-semibold text-fg-muted hover:bg-bg-subtle hover:text-fg-base transition-all shadow-xs active:scale-95"
            >
              <Download size={12} />
              <span>{t.library.download}</span>
            </a>
          )}
        </div>
      </header>

      {/* Viewer Canvas Area */}
      <div className="flex-1 overflow-hidden bg-bg-base">
        {needsHydrate && (
          <div className="flex h-full items-center justify-center p-8 text-center animate-fade-in">
            <div className="max-w-sm rounded-2xl border border-border/80 bg-bg-card p-6 shadow-card">
              <Cloud className="mx-auto h-10 w-10 text-accent mb-2" />
              <h2 className="text-sm font-semibold text-fg-base">{t.library.remoteFileTitle}</h2>
              <p className="mt-1 text-xs text-fg-muted leading-relaxed">{t.library.remoteFileBody}</p>
              {hydrateError && (
                <p className="mt-3 rounded bg-danger-subtle p-2 text-xs text-danger border border-danger/20 font-mono">
                  {hydrateError}
                </p>
              )}
            </div>
          </div>
        )}

        {!needsHydrate && (
          <>
            {kind === "pdf" && (
              <PdfView
                url={contentUrl}
                page={Number.isFinite(pageLoc as number) ? (pageLoc as number) : null}
              />
            )}
            {kind === "image" && <ImageView url={contentUrl} name={name} sizeBytes={meta?.size_bytes} />}
            {kind === "md" && (
              <MdView
                url={contentUrl}
                quote={quoteLoc}
                lineRange={lineLoc}
                onScrolled={onLocatorConsumed}
              />
            )}
            {kind === "text" && (
              <TextView
                url={contentUrl}
                quote={quoteLoc}
                lineRange={lineLoc}
                onScrolled={onLocatorConsumed}
              />
            )}
            {kind === "code" && (
              <CodeView
                url={contentUrl}
                lang={CODE_EXT_TO_LANG[(name.split(".").pop() || "").toLowerCase()] || "text"}
                quote={quoteLoc}
                lineRange={lineLoc}
                onScrolled={onLocatorConsumed}
              />
            )}
            {isOfficeKind(kind) && (
              <OfficeDocumentView
                url={contentUrl}
                format={kind}
                name={name}
                downloadUrl={downloadUrl}
                quote={quoteLoc}
                page={Number.isFinite(pageLoc as number) ? (pageLoc as number) : null}
                block={Number.isFinite(blockLoc as number) ? (blockLoc as number) : null}
                sheet={locator?.sheet || null}
                cell={locator?.cell || null}
                row={Number.isFinite(rowLoc as number) ? (rowLoc as number) : null}
                onScrolled={onLocatorConsumed}
              />
            )}
            {kind === "epub" && (
              <EpubView
                url={contentUrl}
                name={name}
                downloadUrl={downloadUrl}
                quote={quoteLoc}
                page={Number.isFinite(pageLoc as number) ? (pageLoc as number) : null}
                onScrolled={onLocatorConsumed}
              />
            )}
            {kind === "email" && (
              <ExtractedMarkdownView
                entryId={entryId}
                quote={quoteLoc}
                lineRange={lineLoc}
                onScrolled={onLocatorConsumed}
              />
            )}
            {kind === "archive" && <ArchiveView url={downloadUrl} name={name} />}
            {kind === "binary" && <BinaryView url={downloadUrl} name={name} />}
          </>
        )}
      </div>
    </div>
  );
}

function FileHeaderIcon({ kind }: { kind: Kind }) {
  if (kind === "pdf") return <FileText size={15} className="text-rose-500" />;
  if (kind === "md" || kind === "text") return <FileText size={15} className="text-blue-500" />;
  if (kind === "image") return <FileImage size={15} className="text-emerald-500" />;
  if (kind === "code") return <FileCode size={15} className="text-amber-500" />;
  if (kind === "docx" || kind === "xlsx" || kind === "pptx") return <FileSpreadsheet size={15} className="text-indigo-500" />;
  if (kind === "epub") return <Book size={15} className="text-purple-500" />;
  if (kind === "archive") return <FileArchive size={15} className="text-orange-500" />;
  return <FileBox size={15} className="text-fg-subtle" />;
}
