/** Library = a personal file cabinet with metadata.
 *
 *  Three-region layout:
 *    Tree (left, fixed-ish width)  | Viewer (center, fluid) | Meta (right, collapsible)
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useSearchParams } from "react-router-dom";
import { Inbox } from "lucide-react";

import { fileEntries, tasks, webdavSync } from "@/api/client";
import type { ActiveTasks, FileEntrySummary, FileMetadata, Folder, WebDavStatus } from "@/types/api";
import { FolderTree } from "@/components/library/FolderTree";
import { FileViewer, type ViewerLocator } from "@/components/library/FileViewer";
import { MetaPanel } from "@/components/library/MetaPanel";
import { NewFolderDialog, UploadDialog, WebDavSyncDialog } from "@/components/library/Dialogs";
import { useI18n, type I18nStrings } from "@/lib/i18n";

const SIDEBAR_WIDTH_KEY = "library.library.sidebarWidth";
const SIDEBAR_DEFAULT_WIDTH = 290;
const SIDEBAR_MIN_WIDTH = 240;
const SIDEBAR_MAX_WIDTH = 560;

export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedEntry, setSelectedEntry] = useState<FileEntrySummary | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);
  const [meta, setMeta] = useState<FileMetadata | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaOpen, setMetaOpen] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const triggerRefresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const activeFileIdsRef = useRef<Set<string>>(new Set());
  const [expandPath, setExpandPath] = useState<string[]>([]);
  const [pendingEntryId, setPendingEntryId] = useState<string | null>(null);
  const [pendingLocator, setPendingLocator] = useState<ViewerLocator | null>(null);
  const { t } = useI18n();

  const [newFolderUnder, setNewFolderUnder] = useState<{ id: string | null; name: string } | null>(null);
  const [uploadInto, setUploadInto] = useState<{ id: string | null; name: string } | null>(null);

  const [active, setActive] = useState<ActiveTasks | null>(null);
  const [webdav, setWebdav] = useState<WebDavStatus | null>(null);
  const [webdavDialog, setWebdavDialog] = useState<"upload" | "download" | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  const ingestingFileIds = useMemo<Set<string>>(() => {
    const set = new Set<string>();
    if (!active) return set;
    for (const task of active.running) if (task.file_id) set.add(task.file_id);
    for (const task of active.pending) if (task.file_id) set.add(task.file_id);
    return set;
  }, [active]);

  useEffect(() => {
    let cancelled = false;
    const tick = () =>
      tasks.active().then(
        (r) => {
          if (cancelled) return;
          const nextFileIds = activeTaskFileIds(r);
          const settledFileTask = [...activeFileIdsRef.current].some(
            (fileId) => !nextFileIds.has(fileId),
          );
          activeFileIdsRef.current = nextFileIds;
          if (settledFileTask) {
            triggerRefresh();
          }
          setActive(r);
        },
        () => {},
      );
    tick();
    const handle = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [triggerRefresh]);

  useEffect(() => {
    let cancelled = false;
    const tick = () =>
      webdavSync.status().then(
        (s) => {
          if (!cancelled) setWebdav(s);
        },
        () => {},
      );
    tick();
    const handle = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

  useEffect(() => {
    const entryId = searchParams.get("entry");
    if (!entryId) return;
    const quote = searchParams.get("q") || searchParams.get("quote") || undefined;
    const line = searchParams.get("line") || undefined;
    const page = searchParams.get("page") || undefined;
    const block = searchParams.get("block") || undefined;
    const sheet = searchParams.get("sheet") || undefined;
    const cell = searchParams.get("cell") || undefined;
    const row = searchParams.get("row") || undefined;
    const locator: ViewerLocator | null =
      quote || line || page || block || sheet || cell || row
        ? { quote, line, page, block, sheet, cell, row }
        : null;
    const hasLocator = Boolean(locator);
    const locatorParams = ["q", "quote", "line", "page", "block", "sheet", "cell", "row"];

    let cancelled = false;
    fileEntries
      .path(entryId)
      .then(
        (p) => {
          if (cancelled) return;
          setExpandPath(p.ancestors.map((a) => a.id));
          setPendingEntryId(p.entry_id);
          setPendingLocator(hasLocator ? locator : null);
          const next = new URLSearchParams(searchParams);
          next.delete("entry");
          locatorParams.forEach((param) => next.delete(param));
          setSearchParams(next, { replace: true });
        },
        () => {
          if (!cancelled) {
            const next = new URLSearchParams(searchParams);
            next.delete("entry");
            locatorParams.forEach((param) => next.delete(param));
            setSearchParams(next, { replace: true });
          }
        },
      );
    return () => {
      cancelled = true;
    };
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!selectedEntry) {
      setMeta(null);
      return;
    }
    setMeta(null);
    let cancelled = false;
    setMetaLoading(true);
    fileEntries
      .metadata(selectedEntry.id)
      .then((m) => {
        if (!cancelled) setMeta(m);
      })
      .catch(() => {
        if (!cancelled) setMeta(null);
      })
      .finally(() => {
        if (!cancelled) setMetaLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedEntry]);

  const selectFile = useCallback((entry: FileEntrySummary) => {
    setSelectedEntry(entry);
    setSelectedFolder(null);
  }, []);

  const selectFolder = useCallback((folder: Folder | null) => {
    setSelectedFolder(folder);
    setSelectedEntry(null);
    setMeta(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedFolder(null);
    setSelectedEntry(null);
    setMeta(null);
  }, []);

  const handleEntryDeleted = useCallback(
    (entryId: string) => {
      if (selectedEntry?.id === entryId) {
        setSelectedEntry(null);
        setMeta(null);
      }
    },
    [selectedEntry],
  );

  const handleFolderDeleted = useCallback(
    (folderId: string) => {
      if (selectedFolder?.id === folderId) {
        setSelectedFolder(null);
      }
    },
    [selectedFolder],
  );

  const handleResizeStart = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = sidebarWidth;

    const onPointerMove = (moveEvent: PointerEvent) => {
      const next = clampSidebarWidth(startWidth + (moveEvent.clientX - startX));
      setSidebarWidth(next);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(next));
      }
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  };

  return (
    <div className="flex h-full w-full overflow-hidden select-none bg-bg-base">
      {/* Left Tree Explorer */}
      <div
        ref={sidebarRef}
        style={{ width: `${sidebarWidth}px` }}
        className="flex shrink-0 flex-col overflow-hidden border-r border-border/80 bg-bg-subtle/70"
      >
        <FolderTree
          selectedEntryId={selectedEntry?.id ?? null}
          selectedFolderId={selectedFolder?.id ?? null}
          selectedFolderName={selectedFolder?.name ?? null}
          selectedFolderFailedCount={selectedFolder?.ingest_summary?.failed ?? null}
          onSelectFile={selectFile}
          onSelectFolder={selectFolder}
          ingestingFileIds={ingestingFileIds}
          refreshKey={refreshKey}
          expandPath={expandPath}
          pendingEntryId={pendingEntryId}
          onPendingEntryResolved={() => {
            setPendingEntryId(null);
            setExpandPath([]);
          }}
          onUploadHere={(t) =>
            setUploadInto({
              id: t?.id ?? selectedFolder?.id ?? null,
              name: t?.name ?? selectedFolder?.name ?? "Root",
            })
          }
          onNewFolderHere={(t) =>
            setNewFolderUnder({
              id: t?.id ?? selectedFolder?.id ?? null,
              name: t?.name ?? selectedFolder?.name ?? "Root",
            })
          }
          webdav={webdav}
          onWebDavUploadSync={() => setWebdavDialog("upload")}
          onWebDavDownloadSync={() => setWebdavDialog("download")}
          onEntryDeleted={handleEntryDeleted}
          onFolderDeleted={handleFolderDeleted}
          onClearSelection={clearSelection}
        />
      </div>

      {/* Resize Handle */}
      <div
        onPointerDown={handleResizeStart}
        className="group relative flex w-1.5 shrink-0 cursor-col-resize items-center justify-center hover:bg-accent/10 transition-colors"
      >
        <div className="h-8 w-0.5 rounded-full bg-border/60 group-hover:bg-accent group-hover:w-1 transition-all" />
      </div>

      {/* Center Canvas / Viewer */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-bg-base">
        {selectedEntry ? (
          <FileViewer
            entryId={selectedEntry.id}
            meta={meta}
            locator={pendingLocator}
            onLocatorConsumed={() => setPendingLocator(null)}
            onHydrated={triggerRefresh}
          />
        ) : (
          <EmptyViewer folder={selectedFolder} onClick={clearSelection} t={t} />
        )}
      </div>

      {/* Right Meta Drawer */}
      <MetaPanel
        meta={meta}
        loading={metaLoading}
        open={metaOpen}
        onToggle={() => setMetaOpen((o) => !o)}
      />

      {/* Dialog Modals */}
      {newFolderUnder && (
        <NewFolderDialog
          parentId={newFolderUnder.id}
          parentName={newFolderUnder.name}
          onClose={() => setNewFolderUnder(null)}
          onCreated={triggerRefresh}
        />
      )}
      {uploadInto && (
        <UploadDialog
          folderId={uploadInto.id}
          folderName={uploadInto.name}
          onClose={() => setUploadInto(null)}
          onUploaded={triggerRefresh}
        />
      )}
      {webdavDialog && (
        <WebDavSyncDialog
          mode={webdavDialog}
          onClose={() => setWebdavDialog(null)}
          onDone={triggerRefresh}
        />
      )}
    </div>
  );
}

function activeTaskFileIds(active: ActiveTasks): Set<string> {
  const ids = new Set<string>();
  for (const task of active.running) if (task.file_id) ids.add(task.file_id);
  for (const task of active.pending) if (task.file_id) ids.add(task.file_id);
  return ids;
}

function readSidebarWidth(): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT_WIDTH;
  const raw = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
  const parsed = raw ? Number(raw) : NaN;
  return clampSidebarWidth(Number.isFinite(parsed) ? parsed : SIDEBAR_DEFAULT_WIDTH);
}

function clampSidebarWidth(width: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)));
}

function EmptyViewer({
  folder,
  onClick,
  t,
}: {
  folder: Folder | null;
  onClick: () => void;
  t: I18nStrings;
}) {
  return (
    <div
      onClick={onClick}
      className="flex flex-1 cursor-default flex-col items-center justify-center p-8 text-center animate-fade-in"
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-muted text-fg-subtle shadow-subtle border border-border/80">
        <Inbox size={24} strokeWidth={1.8} />
      </div>
      <h2 className="text-base font-semibold text-fg-base tracking-tight">
        {t.library.selectFileTitle(folder?.name ?? null)}
      </h2>
      <p className="mt-1.5 max-w-sm text-xs text-fg-muted leading-relaxed">
        {folder ? t.library.selectFileHint : t.library.emptyHint}
      </p>
    </div>
  );
}
