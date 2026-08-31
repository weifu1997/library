/** Single-pane folder + file tree.
 *
 *  Folders expand on chevron click; files are leaf nodes that select on
 *  click. Folders also select on click (showing the empty viewer +
 *  "select a file" hint). Uses the existing `folders.list` and
 *  `folders.get` endpoints — children are fetched lazily.
 *
 *  Background activity (ingest tasks) lights up an `<Loader2>` next to
 *  any file row whose file_id matches an entry in the active-tasks set.
 */
import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  Folder as FolderIcon,
  FolderOpen,
  FileText,
  Loader2,
  Plus,
  Upload as UploadIcon,
  Download,
  RefreshCw,
  Trash2,
  AlertTriangle,
  CircleDashed,
  CloudDownload,
  CloudUpload,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileBox,
  FileAudio,
  FileVideo,
  FileArchive,
  Book,
} from "lucide-react";

import { folders, fileEntries, files, maybeAuthDownload, ApiError } from "@/api/client";
import type { Folder, FolderIngestSummary, FileEntrySummary, WebDavStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import { useI18n, type I18nStrings } from "@/lib/i18n";

export interface FileNode {
  kind: "file";
  entry: FileEntrySummary;
}
export interface FolderNode {
  kind: "folder";
  folder: Folder;
}
export type Node = FileNode | FolderNode;
export interface FolderActionTarget {
  id: string | null;
  name: string;
}

interface Props {
  selectedEntryId: string | null;
  selectedFolderId: string | null;
  selectedFolderName: string | null;
  selectedFolderFailedCount: number | null;
  onSelectFile: (entry: FileEntrySummary) => void;
  onSelectFolder: (folder: Folder | null) => void;
  ingestingFileIds: Set<string>;
  refreshKey: number;
  /** Force-expand this folder ancestor chain (root → leaf). Each row
   *  whose id appears here opens itself and forwards the *remainder*
   *  of the chain to its children — so a click on a search hit walks
   *  the tree open one level at a time. */
  expandPath?: string[];
  /** When set, the leaf folder selects this file once its contents
   *  load. Cleared via `onPendingEntryResolved` so the same path
   *  doesn't keep re-selecting on subsequent re-renders. */
  pendingEntryId?: string | null;
  onPendingEntryResolved?: () => void;
  onUploadHere: (target: FolderActionTarget | null) => void;
  onNewFolderHere: (target: FolderActionTarget | null) => void;
  webdav?: WebDavStatus | null;
  onWebDavUploadSync?: () => void;
  onWebDavDownloadSync?: () => void;
  onEntryDeleted: (entryId: string) => void;
  onFolderDeleted: (folderId: string) => void;
  onClearSelection: () => void;
}

export function FolderTree(props: Props) {
  const [roots, setRoots] = useState<Folder[] | null>(null);
  const [rootEntries, setRootEntries] = useState<FileEntrySummary[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [reprocessingAll, setReprocessingAll] = useState(false);
  const [reprocessingFailed, setReprocessingFailed] = useState(false);
  const { t } = useI18n();
  const loadGenRef = useRef(0);

  const load = useCallback(() => {
    const gen = ++loadGenRef.current;
    folders.list(null).then(
      (r) => {
        if (gen !== loadGenRef.current) return;
        setRoots(r.folders);
        setRootEntries(r.entries ?? []);
        setErr(null);
      },
      (e) => {
        if (gen !== loadGenRef.current) return;
        setErr(e instanceof Error ? e.message : String(e));
      },
    );
  }, []);

  useEffect(() => {
    load();
  }, [load, props.refreshKey]);

  // Root-level entries: if we're navigating to an entry that lives in
  // the root (empty ancestor chain), the leaf is here, not in any
  // FolderRow — match against the root entries we already have.
  useEffect(() => {
    if (!props.pendingEntryId) return;
    const expanding = props.expandPath && props.expandPath.length > 0;
    if (expanding) return;
    const hit = rootEntries.find((e) => e.id === props.pendingEntryId);
    if (hit) {
      props.onSelectFile(hit);
      props.onPendingEntryResolved?.();
    }
  }, [rootEntries, props.pendingEntryId, props.expandPath, props.onSelectFile, props]);

  const headerTarget = props.selectedFolderName ?? t.library.root;
  const reprocessScope = props.selectedFolderId
    ? ({ folder_id: props.selectedFolderId } as const)
    : ({ all: true } as const);
  const reprocessLabel = props.selectedFolderId
    ? t.library.reprocessFolderConfirm(props.selectedFolderName ?? headerTarget)
    : t.library.reprocessAllConfirm;
  const rootFailedCount = useMemo(() => {
    const folderFailures = (roots ?? []).reduce(
      (sum, folder) => sum + (folder.ingest_summary?.failed ?? 0),
      0,
    );
    const rootEntryFailures = rootEntries.filter((e) => e.ingest_status === "failed").length;
    return folderFailures + rootEntryFailures;
  }, [roots, rootEntries]);
  const scopeFailedCount = props.selectedFolderId
    ? props.selectedFolderFailedCount ?? 0
    : rootFailedCount;
  const failedScope = props.selectedFolderId
    ? ({ folder_id: props.selectedFolderId, status: "failed" } as const)
    : ({ status: "failed" } as const);
  const failedLabel = props.selectedFolderId
    ? t.library.reprocessFailedFolderConfirm(headerTarget, scopeFailedCount)
    : t.library.reprocessFailedAllConfirm(scopeFailedCount);

  const onReprocessScope = async () => {
    if (reprocessingAll) return;
    if (!confirm(reprocessLabel)) return;
    setReprocessingAll(true);
    try {
      const r = await files.reprocessBulk(reprocessScope);
      alert(t.library.queuedReprocess(r.task_ids.length, r.reused_count, r.skipped_count));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      alert(t.library.bulkReprocessFailed(msg));
    } finally {
      setReprocessingAll(false);
    }
  };

  const onReprocessFailedScope = async () => {
    if (reprocessingFailed) return;
    if (!confirm(failedLabel)) return;
    setReprocessingFailed(true);
    try {
      const r = await files.reprocessBulk(failedScope);
      alert(t.library.queuedReprocess(r.task_ids.length, r.reused_count, r.skipped_count));
      load();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      alert(t.library.bulkReprocessFailed(msg));
    } finally {
      setReprocessingFailed(false);
    }
  };

  return (
    <div className="flex h-full flex-col select-none">
      {/* Action Toolbar */}
      <div className="flex h-11 items-center justify-between border-b border-border/80 bg-bg-card/40 px-3 py-1">
        <span
          className="truncate text-xs font-bold text-fg-base max-w-[120px]"
          title={headerTarget}
        >
          {headerTarget}
        </span>
        <div className="flex items-center gap-1">
          {scopeFailedCount > 0 && (
            <button
              onClick={onReprocessFailedScope}
              disabled={reprocessingFailed}
              title={
                props.selectedFolderId
                  ? t.library.reprocessFailedFolderTitle(headerTarget, scopeFailedCount)
                  : t.library.reprocessFailedAllTitle(scopeFailedCount)
              }
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-xl text-danger border border-danger/30 bg-danger-subtle/50 hover:bg-danger-subtle active:scale-95 disabled:opacity-50 transition-all shadow-2xs"
            >
              {reprocessingFailed ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <AlertTriangle size={14} />
              )}
            </button>
          )}
          <button
            onClick={onReprocessScope}
            disabled={reprocessingAll}
            title={
              props.selectedFolderId
                ? t.library.reprocessFolderTitle(headerTarget)
                : t.library.reprocessAllTitle
            }
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-xl text-fg-muted border border-border/70 bg-bg-card hover:bg-bg-subtle hover:text-fg-base active:scale-95 disabled:opacity-50 transition-all shadow-2xs"
          >
            {reprocessingAll ? (
              <Loader2 size={14} className="animate-spin text-accent" />
            ) : (
              <RefreshCw size={14} />
            )}
          </button>
          <button
            onClick={() => props.onWebDavDownloadSync?.()}
            disabled={!props.webdav?.configured}
            title={
              props.webdav?.configured
                ? webdavDownloadTitle(props.webdav, t)
                : t.library.webdavNotConfigured
            }
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-xl text-fg-muted border border-border/70 bg-bg-card hover:bg-bg-subtle hover:text-fg-base active:scale-95 disabled:opacity-50 transition-all shadow-2xs"
          >
            <CloudDownload size={14} />
          </button>
          <button
            onClick={() => props.onWebDavUploadSync?.()}
            disabled={!props.webdav?.configured}
            title={
              props.webdav?.configured
                ? webdavUploadTitle(props.webdav, t)
                : t.library.webdavNotConfigured
            }
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-xl text-fg-muted border border-border/70 bg-bg-card hover:bg-bg-subtle hover:text-fg-base active:scale-95 disabled:opacity-50 transition-all shadow-2xs"
          >
            <CloudUpload size={14} />
          </button>
          <button
            onClick={() => props.onNewFolderHere(null)}
            title={t.library.newFolderIn(headerTarget)}
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted hover:bg-bg-subtle hover:text-fg-base active:scale-95 transition-all"
          >
            <Plus size={14} />
          </button>
          <button
            onClick={() => props.onUploadHere(null)}
            title={t.library.uploadTo(headerTarget)}
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted hover:bg-bg-subtle hover:text-fg-base active:scale-95 transition-all"
          >
            <UploadIcon size={14} />
          </button>
        </div>
      </div>

      {err && (
        <div className="m-2 rounded-xl bg-danger-subtle p-2.5 text-xs text-danger border border-danger/20">
          {err}
        </div>
      )}

      {/* Tree Content */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
        {roots === null ? (
          <div className="flex items-center justify-center py-10 text-xs text-fg-subtle gap-2">
            <Loader2 size={14} className="animate-spin text-accent" />
            <span>{t.common.loading}</span>
          </div>
        ) : roots.length === 0 && rootEntries.length === 0 ? (
          <div className="py-12 px-4 text-center text-xs text-fg-subtle leading-relaxed">
            {t.library.emptyTree}
          </div>
        ) : (
          <>
            {roots.map((f) => (
              <FolderRow
                key={f.id}
                folder={f}
                depth={0}
                selectedEntryId={props.selectedEntryId}
                selectedFolderId={props.selectedFolderId}
                selectedFolderName={props.selectedFolderName}
                selectedFolderFailedCount={props.selectedFolderFailedCount}
                onSelectFile={props.onSelectFile}
                onSelectFolder={props.onSelectFolder}
                ingestingFileIds={props.ingestingFileIds}
                refreshKey={props.refreshKey}
                expandPath={props.expandPath}
                pendingEntryId={props.pendingEntryId}
                onPendingEntryResolved={props.onPendingEntryResolved}
                onUploadHere={props.onUploadHere}
                onNewFolderHere={props.onNewFolderHere}
                onEntryDeleted={props.onEntryDeleted}
                onFolderReprocessed={load}
                onFolderDeleted={(id) => {
                  load();
                  props.onFolderDeleted(id);
                }}
                onClearSelection={props.onClearSelection}
              />
            ))}
            {rootEntries.map((e) => (
              <FileRow
                key={e.id}
                entry={e}
                depth={0}
                selected={props.selectedEntryId === e.id}
                ingesting={props.ingestingFileIds.has(e.file_id)}
                onClick={() => props.onSelectFile(e)}
                onDeleted={(id) => {
                  load();
                  props.onEntryDeleted(id);
                }}
                onReprocessed={load}
                t={t}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

interface FolderRowProps extends Props {
  folder: Folder;
  depth: number;
  onFolderReprocessed: () => void;
}

function FolderRow(props: FolderRowProps) {
  const { folder, depth } = props;
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<Folder[] | null>(null);
  const [entries, setEntries] = useState<FileEntrySummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reprocessingFolder, setReprocessingFolder] = useState(false);
  const [reprocessingFailedFolder, setReprocessingFailedFolder] = useState(false);
  const loadedRef = useRef(false);
  const detailGenRef = useRef(0);
  const { t } = useI18n();

  const loadDetail = useCallback(
    (showSpinner = !loadedRef.current) => {
      const gen = ++detailGenRef.current;
      if (showSpinner) setLoading(true);
      return folders.get(folder.id).then(
        (d) => {
          if (gen !== detailGenRef.current) return;
          loadedRef.current = true;
          setChildren(d.children);
          setEntries(d.entries);
          setLoading(false);
        },
        () => {
          if (gen !== detailGenRef.current) return;
          setLoading(false);
        },
      );
    },
    [folder.id],
  );

  const refreshAfterSubtreeReprocess = useCallback(() => {
    props.onFolderReprocessed();
    if (loadedRef.current) {
      void loadDetail(false);
    }
  }, [loadDetail, props]);

  const onPath = props.expandPath?.[0] === folder.id;
  useEffect(() => {
    if (onPath && !open) setOpen(true);
  }, [onPath, open]);

  useEffect(() => {
    if (open) loadDetail();
  }, [open, loadDetail, props.refreshKey]);

  const isLeaf = onPath && props.expandPath?.length === 1;
  useEffect(() => {
    if (!isLeaf || !props.pendingEntryId || entries === null) return;
    const hit = entries.find((e) => e.id === props.pendingEntryId);
    if (hit) {
      props.onSelectFile(hit);
      props.onPendingEntryResolved?.();
    }
  }, [isLeaf, props.pendingEntryId, entries, props]);

  const childExpandPath = onPath ? props.expandPath!.slice(1) : props.expandPath;
  const isSelected = props.selectedFolderId === folder.id;
  const folderFailed = (folder.ingest_summary?.failed ?? 0) > 0;
  const indent = { paddingLeft: 6 + depth * 14 };

  const onDeleteFolder = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleting) return;
    if (!confirm(t.library.deleteFolderConfirm(folder.name))) return;
    setDeleting(true);
    try {
      await folders.delete(folder.id);
      props.onFolderDeleted(folder.id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      alert(t.library.deleteFailed(msg));
      setDeleting(false);
    }
  };

  const onReprocessFolder = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (reprocessingFolder) return;
    if (!confirm(t.library.reprocessFolderConfirm(folder.name))) return;
    setReprocessingFolder(true);
    try {
      const r = await files.reprocessBulk({ folder_id: folder.id });
      alert(t.library.queuedReprocess(r.task_ids.length, r.reused_count, r.skipped_count));
      refreshAfterSubtreeReprocess();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      alert(t.library.bulkReprocessFailed(msg));
    } finally {
      setReprocessingFolder(false);
    }
  };

  const onReprocessFailedFolder = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (reprocessingFailedFolder) return;
    const failedCount = folder.ingest_summary?.failed ?? 0;
    if (!confirm(t.library.reprocessFailedFolderConfirm(folder.name, failedCount))) return;
    setReprocessingFailedFolder(true);
    try {
      const r = await files.reprocessBulk({ folder_id: folder.id, status: "failed" });
      alert(t.library.queuedReprocess(r.task_ids.length, r.reused_count, r.skipped_count));
      refreshAfterSubtreeReprocess();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      alert(t.library.bulkReprocessFailed(msg));
    } finally {
      setReprocessingFailedFolder(false);
    }
  };

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-xl py-1.5 pr-2 text-xs transition-colors cursor-pointer",
          isSelected
            ? "bg-bg-elevated text-fg-base shadow-xs ring-1 ring-border/80 font-medium"
            : "text-fg-muted hover:bg-bg-muted/50 hover:text-fg-base",
        )}
        style={indent}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            setOpen((o) => !o);
          }}
          className="flex h-5 w-5 items-center justify-center rounded p-0.5 text-fg-subtle hover:bg-bg-base/70 hover:text-fg-base transition-colors shrink-0"
          type="button"
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button>

        <button
          onClick={() => props.onSelectFolder(isSelected ? null : folder)}
          className="flex flex-1 items-center gap-2 truncate text-left"
          type="button"
        >
          {open ? (
            <FolderOpen size={14} className="text-accent shrink-0" />
          ) : (
            <FolderIcon size={14} className="text-accent/80 shrink-0" />
          )}
          <span className="min-w-0 flex-1 truncate font-medium">{folder.name}</span>
          <FolderIngestBadge summary={folder.ingest_summary} t={t} />
        </button>

        <div
          className={cn(
            "items-center gap-0.5 shrink-0",
            folderFailed || reprocessingFolder || reprocessingFailedFolder
              ? "flex"
              : "hidden group-hover:flex",
          )}
        >
          {folderFailed && (
            <button
              onClick={onReprocessFailedFolder}
              disabled={reprocessingFailedFolder}
              title={t.library.reprocessFailedFolderTitle(
                folder.name,
                folder.ingest_summary?.failed ?? 0,
              )}
              className="flex h-6.5 w-6.5 items-center justify-center rounded text-danger hover:bg-danger-subtle active:scale-95 disabled:opacity-50 transition-colors"
              type="button"
            >
              {reprocessingFailedFolder ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <AlertTriangle size={11} />
              )}
            </button>
          )}
          <button
            onClick={onReprocessFolder}
            disabled={reprocessingFolder}
            title={t.library.reprocessFolderTitle(folder.name)}
            className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-fg-base active:scale-95 disabled:opacity-50 transition-colors"
            type="button"
          >
            {reprocessingFolder ? (
              <Loader2 size={11} className="animate-spin text-accent" />
            ) : (
              <RefreshCw size={11} />
            )}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              props.onNewFolderHere({ id: folder.id, name: folder.name });
            }}
            title={t.library.newSubfolder}
            className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-fg-base active:scale-95 transition-colors"
            type="button"
          >
            <Plus size={11} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              props.onUploadHere({ id: folder.id, name: folder.name });
            }}
            title={t.library.uploadHere}
            className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-fg-base active:scale-95 transition-colors"
            type="button"
          >
            <UploadIcon size={11} />
          </button>
          <button
            onClick={onDeleteFolder}
            disabled={deleting}
            title={t.library.deleteFolder}
            className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-danger active:scale-95 disabled:opacity-50 transition-colors"
            type="button"
          >
            {deleting ? (
              <Loader2 size={11} className="animate-spin" />
            ) : (
              <Trash2 size={11} />
            )}
          </button>
        </div>
      </div>

      {open && (
        <div>
          {loading && (
            <div
              style={{ paddingLeft: 6 + (depth + 1) * 14 }}
              className="py-1 text-xs text-fg-subtle"
            >
              …
            </div>
          )}
          {children?.map((c) => (
            <FolderRow
              key={c.id}
              folder={c}
              depth={depth + 1}
              selectedEntryId={props.selectedEntryId}
              selectedFolderId={props.selectedFolderId}
              selectedFolderName={props.selectedFolderName}
              selectedFolderFailedCount={props.selectedFolderFailedCount}
              onSelectFile={props.onSelectFile}
              onSelectFolder={props.onSelectFolder}
              ingestingFileIds={props.ingestingFileIds}
              refreshKey={props.refreshKey}
              expandPath={childExpandPath}
              pendingEntryId={props.pendingEntryId}
              onPendingEntryResolved={props.onPendingEntryResolved}
              onUploadHere={props.onUploadHere}
              onNewFolderHere={props.onNewFolderHere}
              onEntryDeleted={props.onEntryDeleted}
              onFolderReprocessed={refreshAfterSubtreeReprocess}
              onFolderDeleted={(id) => {
                loadDetail();
                props.onFolderDeleted(id);
              }}
              onClearSelection={props.onClearSelection}
            />
          ))}
          {entries?.map((e) => (
            <FileRow
              key={e.id}
              entry={e}
              depth={depth + 1}
              selected={props.selectedEntryId === e.id}
              ingesting={props.ingestingFileIds.has(e.file_id)}
              onClick={() => props.onSelectFile(e)}
              onDeleted={(id) => {
                loadDetail();
                props.onEntryDeleted(id);
              }}
              onReprocessed={refreshAfterSubtreeReprocess}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FolderIngestBadge({
  summary,
  t,
}: {
  summary?: FolderIngestSummary | null;
  t: I18nStrings;
}) {
  if (!summary || summary.total <= 0 || summary.incomplete <= 0) return null;

  const failed = summary.failed > 0;
  const processing = !failed && summary.processing > 0;
  const count = failed ? summary.failed : summary.incomplete;
  const label = failed
    ? t.library.folderFailedBadge(summary.failed)
    : t.library.folderUnfinishedBadge(summary.incomplete);
  const title = t.library.folderIngestSummary(
    summary.total,
    summary.done,
    summary.pending,
    summary.processing,
    summary.failed,
  );

  return (
    <span
      title={title}
      aria-label={label}
      className={cn(
        "inline-flex h-4 shrink-0 items-center gap-0.5 rounded border px-1 text-[10px] leading-none tabular-nums font-semibold",
        failed
          ? "border-danger/30 bg-danger/10 text-danger"
          : "border-border bg-bg-muted text-fg-muted",
      )}
    >
      {failed ? (
        <AlertTriangle size={10} />
      ) : processing ? (
        <Loader2 size={10} className="animate-spin" />
      ) : (
        <CircleDashed size={10} />
      )}
      <span>{count}</span>
    </span>
  );
}

function FileRow({
  entry,
  depth,
  selected,
  ingesting,
  onClick,
  onDeleted,
  onReprocessed,
  t,
}: {
  entry: FileEntrySummary;
  depth: number;
  selected: boolean;
  ingesting: boolean;
  onClick: () => void;
  onDeleted: (entryId: string) => void;
  onReprocessed: () => void;
  t: I18nStrings;
}) {
  const [reprocessing, setReprocessing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const failed = entry.ingest_status === "failed";
  const failureTitle = failed && entry.ingest_error
    ? t.library.ingestFailedReason(entry.ingest_error)
    : t.library.ingestFailed;
  const blockedByIngest = ingesting && !failed;
  const reprocessTitle = failed
    ? `${t.library.retryAnalysisTitle}\n${failureTitle}`
    : t.library.reprocessAnalysisTitle;

  const onReprocess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (reprocessing || blockedByIngest) return;
    const prompt = failed
      ? t.library.retryAnalysisConfirm(entry.display_name)
      : t.library.reprocessFileConfirm(entry.display_name);
    if (!confirm(prompt)) {
      return;
    }
    setReprocessing(true);
    try {
      await files.reprocess(entry.file_id);
      onReprocessed();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      alert(t.library.reprocessFailed(msg));
    } finally {
      setReprocessing(false);
    }
  };

  const onDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleting) return;
    if (!confirm(t.library.deleteFileConfirm(entry.display_name))) {
      return;
    }
    setDeleting(true);
    try {
      await fileEntries.delete(entry.id);
      onDeleted(entry.id);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      alert(t.library.deleteFailed(msg));
      setDeleting(false);
    }
  };

  return (
    <div
      style={{ paddingLeft: 6 + depth * 14 + 16 }}
      className={cn(
        "group flex w-full items-center gap-1.5 rounded-xl py-1.5 pr-2 text-xs transition-colors",
        selected
          ? "bg-bg-elevated text-fg-base shadow-xs ring-1 ring-border/80 font-medium"
          : "text-fg-muted hover:bg-bg-muted/50 hover:text-fg-base",
      )}
    >
      <button
        onClick={onClick}
        className="flex flex-1 items-center gap-2 truncate text-left"
        type="button"
      >
        <FileTypeIcon name={entry.display_name} />
        <span className="flex-1 truncate">{entry.display_name}</span>
        {failed && (
          <span
            className="shrink-0 text-danger"
            title={failureTitle}
            aria-label={failureTitle}
          >
            <AlertTriangle size={11} />
          </span>
        )}
      </button>

      {blockedByIngest && (
        <Loader2 size={11} className="shrink-0 animate-spin text-accent" />
      )}

      <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
        <button
          onClick={onReprocess}
          disabled={reprocessing || blockedByIngest}
          title={reprocessTitle}
          className={cn(
            "flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base active:scale-95 disabled:opacity-50 transition-colors",
            failed
              ? "text-danger hover:bg-danger-subtle hover:text-danger"
              : "hover:text-fg-base",
          )}
          type="button"
        >
          {reprocessing ? (
            <Loader2 size={11} className="animate-spin text-accent" />
          ) : (
            <RefreshCw size={11} />
          )}
        </button>
        <a
          href={fileEntries.downloadUrl(entry.id)}
          download={entry.display_name}
          onClick={(e) => {
            e.stopPropagation();
            maybeAuthDownload(e, fileEntries.downloadUrl(entry.id), entry.display_name);
          }}
          title={t.library.download}
          className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-fg-base active:scale-95 transition-colors"
        >
          <Download size={11} />
        </a>
        <button
          onClick={onDelete}
          disabled={deleting}
          title={t.common.delete}
          className="flex h-6.5 w-6.5 items-center justify-center rounded text-fg-subtle hover:bg-bg-base hover:text-danger active:scale-95 disabled:opacity-50 transition-colors"
          type="button"
        >
          {deleting ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Trash2 size={11} />
          )}
        </button>
      </div>
    </div>
  );
}

function FileTypeIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";

  if (ext === "pdf") {
    return <FileText size={14} className="shrink-0 text-rose-500" />;
  }
  if (["md", "markdown", "txt", "rtf"].includes(ext)) {
    return <FileText size={14} className="shrink-0 text-blue-500" />;
  }
  if (["png", "jpg", "jpeg", "webp", "gif", "svg", "heic", "tiff"].includes(ext)) {
    return <FileImage size={14} className="shrink-0 text-emerald-500" />;
  }
  if (["py", "ts", "tsx", "js", "jsx", "json", "yaml", "yml", "html", "css", "rs", "go", "java", "c", "cpp"].includes(ext)) {
    return <FileCode size={14} className="shrink-0 text-amber-500" />;
  }
  if (["xlsx", "xls", "csv", "tsv"].includes(ext)) {
    return <FileSpreadsheet size={14} className="shrink-0 text-teal-600" />;
  }
  if (["docx", "doc", "pptx", "ppt"].includes(ext)) {
    return <FileText size={14} className="shrink-0 text-indigo-500" />;
  }
  if (["epub", "mobi"].includes(ext)) {
    return <Book size={14} className="shrink-0 text-purple-500" />;
  }
  if (["zip", "tar", "gz", "7z", "rar"].includes(ext)) {
    return <FileArchive size={14} className="shrink-0 text-orange-500" />;
  }
  if (["mp3", "wav", "flac", "ogg", "m4a"].includes(ext)) {
    return <FileAudio size={14} className="shrink-0 text-cyan-500" />;
  }
  if (["mp4", "mov", "avi", "mkv", "webm"].includes(ext)) {
    return <FileVideo size={14} className="shrink-0 text-violet-500" />;
  }
  return <FileBox size={14} className="shrink-0 text-fg-subtle" />;
}

function webdavUploadTitle(status: WebDavStatus, t: I18nStrings): string {
  if (status.last?.finished_at) {
    return t.library.webdavLastUploaded(new Date(status.last.finished_at).toLocaleString());
  }
  return t.library.webdavUploadNow;
}

function webdavDownloadTitle(status: WebDavStatus, t: I18nStrings): string {
  if (status.last?.last_download_at) {
    return t.library.webdavLastPulled(new Date(status.last.last_download_at).toLocaleString());
  }
  return t.library.webdavPullNow;
}
