/** Two modal dialogs used by the library page:
 *
 *    NewFolderDialog  — name input, creates under given parent
 *    UploadDialog     — file picker + drag-drop, uploads to given folder
 *                       with progress and conflict-handling. Dropping a
 *                       folder walks the directory tree (webkitGetAsEntry)
 *                       and recreates the subfolder structure under the
 *                       target via /v1/folders before uploading each file.
 *    WebDavSyncDialog — selective WebDAV upload or download sync with plan overview
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { X, Upload, Download, FolderPlus, Loader2, AlertCircle, CheckCircle2, FileText } from "lucide-react";

import { folders as foldersApi, uploads, ApiError, settings as settingsApi, webdavSync } from "@/api/client";
import type { OnConflict, WebDavPlanResult, WebDavSyncLast } from "@/types/api";
import { cn, formatBytes } from "@/lib/utils";
import { useI18n, type I18nStrings } from "@/lib/i18n";

export function NewFolderDialog({
  parentId,
  parentName,
  onClose,
  onCreated,
}: {
  parentId: string | null;
  parentName: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = async () => {
    const v = name.trim();
    if (!v) return;
    setBusy(true);
    setErr(null);
    try {
      await foldersApi.create(v, parentId);
      onCreated();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title={
        <>
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent">
            <FolderPlus size={18} />
          </div>
          <span>{t.library.newFolderIn(parentName)}</span>
        </>
      }
      onClose={onClose}
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-fg-muted">
            {t.dialogs.folderName}
          </label>
          <input
            ref={inputRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder={t.dialogs.folderName}
            className="h-11 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3.5 text-sm font-medium outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all text-fg-base placeholder:text-fg-subtle"
          />
        </div>

        {err && (
          <div className="flex items-start gap-2.5 rounded-xl bg-danger-subtle p-3 text-xs text-danger border border-danger/20">
            <AlertCircle size={15} className="shrink-0 mt-0.5" />
            <span>{err}</span>
          </div>
        )}

        <div className="flex justify-end gap-2.5 pt-3 border-t border-border/60">
          <button
            onClick={onClose}
            type="button"
            className="h-11 rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-muted hover:bg-bg-subtle hover:text-fg-base active:scale-95 transition-all shadow-xs"
          >
            {t.common.cancel}
          </button>
          <button
            onClick={submit}
            disabled={busy || !name.trim()}
            type="button"
            className={cn(
              "h-11 rounded-xl px-5 text-xs font-semibold shadow-xs transition-all active:scale-95 flex items-center justify-center gap-2",
              busy || !name.trim()
                ? "cursor-not-allowed bg-bg-muted text-fg-subtle opacity-70"
                : "bg-accent text-accent-fg hover:bg-accent-hover shadow-indigo-500/20",
            )}
          >
            {busy && <Loader2 size={13} className="animate-spin" />}
            {busy ? t.common.creating : t.common.create}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

interface UploadItem {
  file: File;
  relDirs: string[];
  loaded: number;
  selected: boolean;
  status: "queued" | "uploading" | "done" | "error";
  err?: string;
  renamedTo?: string;
}

type UploadCategory =
  | "documents"
  | "pdfs"
  | "images"
  | "archives"
  | "audio"
  | "videos"
  | "unknown";

interface UploadGroup {
  category: UploadCategory;
  files: number;
  bytes: number;
  selectedFiles: number;
  selectedBytes: number;
  extensions: {
    ext: string;
    files: number;
    bytes: number;
    selectedFiles: number;
    selectedBytes: number;
  }[];
}

const CATEGORY_ORDER: UploadCategory[] = [
  "documents",
  "pdfs",
  "images",
  "archives",
  "audio",
  "videos",
  "unknown",
];
const DEFAULT_INCLUDED_CATEGORIES: UploadCategory[] = CATEGORY_ORDER.filter(
  (c) => c !== "videos",
);

export function UploadDialog({
  folderId,
  folderName,
  onClose,
  onUploaded,
}: {
  folderId: string | null;
  folderName: string;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [conflict, setConflict] = useState<OnConflict>("rename");
  const [running, setRunning] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    settingsApi.server().then(
      (s) => {
        if (cancelled) return;
        const v = s.default_on_conflict as OnConflict;
        if (v === "rename" || v === "error" || v === "skip") setConflict(v);
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const addFiles = (filesList: FileList | File[]) => {
    const raw = Array.from(filesList);
    setItems((prev) => [
      ...prev,
      ...raw.map((f) => ({
        file: f,
        relDirs: [],
        loaded: 0,
        selected: DEFAULT_INCLUDED_CATEGORIES.includes(categoryForFile(f)),
        status: "queued" as const,
      })),
    ]);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dt = e.dataTransfer;
    const entries: FileSystemEntry[] = [];
    if (dt.items) {
      for (let i = 0; i < dt.items.length; i++) {
        const entry = dt.items[i].webkitGetAsEntry?.();
        if (entry) entries.push(entry);
      }
    }
    if (entries.length > 0) {
      setScanning(true);
      try {
        const out: UploadItem[] = [];
        for (const entry of entries) {
          await walkEntry(entry, [], out);
        }
        setItems((prev) => [...prev, ...out]);
      } finally {
        setScanning(false);
      }
      return;
    }
    if (dt.files?.length) addFiles(dt.files);
  };

  const uploadPlan = useMemo(() => {
    const groupsMap = new Map<UploadCategory, {
      files: number;
      bytes: number;
      selectedFiles: number;
      selectedBytes: number;
      extMap: Map<string, { files: number; bytes: number; selectedFiles: number; selectedBytes: number }>;
    }>();

    for (const cat of CATEGORY_ORDER) {
      groupsMap.set(cat, {
        files: 0,
        bytes: 0,
        selectedFiles: 0,
        selectedBytes: 0,
        extMap: new Map(),
      });
    }

    let selectedFiles = 0;
    let selectedBytes = 0;
    let totalFiles = 0;
    let totalBytes = 0;

    for (const it of items) {
      const cat = categoryForFile(it.file);
      const ext = extensionForFile(it.file);
      const g = groupsMap.get(cat)!;
      g.files += 1;
      g.bytes += it.file.size;
      totalFiles += 1;
      totalBytes += it.file.size;

      let e = g.extMap.get(ext);
      if (!e) {
        e = { files: 0, bytes: 0, selectedFiles: 0, selectedBytes: 0 };
        g.extMap.set(ext, e);
      }
      e.files += 1;
      e.bytes += it.file.size;

      if (it.selected) {
        selectedFiles += 1;
        selectedBytes += it.file.size;
        g.selectedFiles += 1;
        g.selectedBytes += it.file.size;
        e.selectedFiles += 1;
        e.selectedBytes += it.file.size;
      }
    }

    const groups: UploadGroup[] = CATEGORY_ORDER
      .map((cat) => {
        const g = groupsMap.get(cat)!;
        return {
          category: cat,
          files: g.files,
          bytes: g.bytes,
          selectedFiles: g.selectedFiles,
          selectedBytes: g.selectedBytes,
          extensions: Array.from(g.extMap.entries()).map(([ext, stats]) => ({
            ext,
            ...stats,
          })),
        };
      })
      .filter((g) => g.files > 0);

    return {
      groups,
      selectedFiles,
      selectedBytes,
      totalFiles,
      totalBytes,
      skippedFiles: totalFiles - selectedFiles,
      skippedBytes: totalBytes - selectedBytes,
    };
  }, [items]);

  const toggleAll = () => {
    if (running) return;
    const allSelected = items.length > 0 && items.every((it) => it.selected);
    setItems((prev) => prev.map((it) => ({ ...it, selected: !allSelected })));
  };

  const toggleCategory = (category: UploadCategory) => {
    if (running) return;
    const matching = items.filter((it) => categoryForFile(it.file) === category);
    const someSelected = matching.some((it) => it.selected);
    setItems((prev) =>
      prev.map((it) =>
        categoryForFile(it.file) === category ? { ...it, selected: !someSelected } : it,
      ),
    );
  };

  const toggleItem = (idx: number) => {
    if (running) return;
    setItems((prev) =>
      prev.map((it, i) => (i === idx ? { ...it, selected: !it.selected } : it)),
    );
  };

  const start = async () => {
    if (running) return;
    setRunning(true);
    let didUpload = false;
    const folderCache = new Map<string, string | null>([["", folderId]]);

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (!item.selected || item.status === "done") continue;
      setItems((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: "uploading" } : it)),
      );
      try {
        const targetFolderId = await mkdirP(folderCache, item.relDirs);
        const dest = targetFolderId
          ? ({ folderId: targetFolderId } as const)
          : ({ remotePath: "/" + item.file.name } as const);

        const res = await uploads.upload(item.file, dest, {
          onConflict: conflict,
          onProgress: (loaded) => {
            setItems((prev) =>
              prev.map((it, idx) => (idx === i ? { ...it, loaded } : it)),
            );
          },
        });
        setItems((prev) =>
          prev.map((it, idx) =>
            idx === i
              ? {
                  ...it,
                  status: "done",
                  loaded: item.file.size,
                  renamedTo: res.auto_renamed ? res.display_name : undefined,
                }
              : it,
          ),
        );
        didUpload = true;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setItems((prev) =>
          prev.map((it, idx) =>
            idx === i ? { ...it, status: "error", err: msg } : it,
          ),
        );
      }
    }
    setRunning(false);
    if (didUpload) onUploaded();
  };

  const selectedCount = items.filter((it) => it.selected).length;
  const doneCount = items.filter((it) => it.status === "done").length;
  const allDone = selectedCount > 0 && doneCount === selectedCount;

  return (
    <ModalShell
      title={
        <>
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent">
            <Upload size={18} />
          </div>
          <span>{t.library.uploadTo(folderName)}</span>
        </>
      }
      onClose={onClose}
      wide
    >
      <div className="space-y-4">
        {/* Drag Drop Zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInput.current?.click()}
          className={cn(
            "flex min-h-[140px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition-all",
            dragOver
              ? "border-accent bg-accent/10 scale-[1.01]"
              : "border-border/80 bg-bg-subtle/50 hover:border-accent/40 hover:bg-bg-subtle/80",
          )}
        >
          <input
            ref={fileInput}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
            }}
          />
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent border border-accent/20 mb-2.5">
            <Upload size={22} strokeWidth={2.2} />
          </div>
          <p className="text-xs font-semibold text-fg-base">
            {scanning ? t.dialogs.scanningFolder : t.dialogs.uploadDrop}
          </p>
          <p className="mt-1 text-[11px] text-fg-subtle">
            {t.dialogs.uploadAnalysisHint}
          </p>
        </div>

        {/* File Filter & Group Selector */}
        {items.length > 0 && (
          <div className="rounded-2xl border border-border/80 bg-bg-subtle/40 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-2.5 bg-bg-card/50">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-fg-base select-none">
                <input
                  type="checkbox"
                  checked={items.length > 0 && items.every((it) => it.selected)}
                  disabled={running}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-border text-accent focus:ring-accent/20"
                />
                <span>{t.dialogs.uploadFilterTitle}</span>
              </label>

              <div className="flex items-center gap-2 text-xs text-fg-muted font-medium">
                <span>
                  {t.dialogs.uploadPlan(uploadPlan.selectedFiles, uploadPlan.skippedFiles)}
                  {" · "}
                  {formatBytes(uploadPlan.selectedBytes)}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {uploadPlan.groups.map((group) => {
                  const allInGroup = group.selectedFiles === group.files;
                  const someInGroup = group.selectedFiles > 0;
                  return (
                    <button
                      key={group.category}
                      type="button"
                      onClick={() => toggleCategory(group.category)}
                      disabled={running}
                      className={cn(
                        "h-7 rounded-lg px-2.5 text-[11px] font-semibold transition-all active:scale-95 flex items-center gap-1.5",
                        allInGroup
                          ? "bg-accent/15 text-accent border border-accent/30"
                          : someInGroup
                            ? "bg-bg-card text-fg-base border border-border"
                            : "bg-transparent text-fg-subtle hover:bg-bg-muted hover:text-fg-muted",
                      )}
                    >
                      {t.dialogs.uploadCategories[group.category]}
                      <span className="text-[10px] opacity-75">({group.files})</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* File List Table */}
            <div className="max-h-60 overflow-y-auto divide-y divide-border/40">
              {items.map((it, idx) => (
                <div
                  key={idx}
                  onClick={() => toggleItem(idx)}
                  className={cn(
                    "flex items-center justify-between px-4 py-2.5 text-xs transition-colors cursor-pointer select-none",
                    it.selected ? "bg-bg-card/40 hover:bg-bg-card/70" : "opacity-50 hover:opacity-75 bg-transparent",
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0 pr-2">
                    <input
                      type="checkbox"
                      checked={it.selected}
                      disabled={running}
                      onChange={() => toggleItem(idx)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-4 w-4 rounded border-border text-accent focus:ring-accent/20"
                    />
                    <FileText size={15} className="shrink-0 text-fg-muted" />
                    <span className="truncate font-medium text-fg-base">{it.file.name}</span>
                    {it.renamedTo && (
                      <span className="text-[10px] text-accent font-semibold">
                        ({t.dialogs.renamedTo(it.renamedTo)})
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0 text-[11px] font-medium text-fg-muted">
                    <span>{formatBytes(it.file.size)}</span>
                    {it.status === "uploading" && (
                      <span className="flex items-center gap-1 text-accent">
                        <Loader2 size={11} className="animate-spin" />
                        {it.loaded ? `${Math.round((it.loaded / it.file.size) * 100)}%` : t.dialogs.uploading}
                      </span>
                    )}
                    {it.status === "done" && (
                      <span className="flex items-center gap-1 text-emerald-500 font-semibold">
                        <CheckCircle2 size={13} />
                        {t.dialogs.done}
                      </span>
                    )}
                    {it.status === "error" && (
                      <span className="text-danger font-semibold" title={it.err}>
                        {t.dialogs.conflict.error}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/60">
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-fg-muted">{t.dialogs.onConflict}</label>
            <div className="grid grid-cols-3 gap-1 rounded-xl border border-border/80 bg-bg-card p-1 shadow-2xs min-w-[210px]">
              {(["rename", "skip", "error"] as OnConflict[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setConflict(p)}
                  disabled={running}
                  className={cn(
                    "flex h-8 items-center justify-center rounded-lg px-2.5 text-xs font-semibold transition-all active:scale-95",
                    conflict === p
                      ? "bg-accent text-accent-fg shadow-xs font-bold"
                      : "text-fg-muted hover:text-fg-base",
                  )}
                >
                  {t.dialogs.conflict[p]}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={onClose}
              type="button"
              className="h-11 rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-muted hover:bg-bg-subtle hover:text-fg-base active:scale-95 transition-all shadow-xs"
            >
              {allDone ? t.common.close : t.common.cancel}
            </button>
            <button
              onClick={start}
              disabled={running || selectedCount === 0 || allDone}
              type="button"
              className={cn(
                "h-11 rounded-xl px-5 text-xs font-semibold shadow-xs transition-all active:scale-95 flex items-center justify-center gap-2",
                running || selectedCount === 0 || allDone
                  ? "cursor-not-allowed bg-bg-muted text-fg-subtle opacity-70"
                  : "bg-accent text-accent-fg hover:bg-accent-hover shadow-indigo-500/20",
              )}
            >
              {running ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>{t.dialogs.uploading}</span>
                </>
              ) : (
                <>
                  <span>{t.dialogs.start} ({selectedCount})</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </ModalShell>
  );
}

export function WebDavSyncDialog({
  mode,
  onClose,
  onDone,
}: {
  mode: "upload" | "download";
  onClose: () => void;
  onDone: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<WebDavPlanResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningStatus, setRunningStatus] = useState<WebDavSyncLast | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isUpload = mode === "upload";
  const title = isUpload
    ? t.library.webdavUploadSyncTitle
    : t.library.webdavDownloadSyncTitle;
  const TitleIcon = isUpload ? Upload : Download;

  const refreshPlan = async () => {
    setLoading(true);
    setErr(null);
    try {
      const nextPlan = isUpload
        ? await webdavSync.uploadPlan()
        : await webdavSync.downloadPlan();
      setPlan(nextPlan);
      setSelected(new Set(nextPlan.items.map((item) => item.entry_id)));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const tick = () =>
      webdavSync.status().then(
        (status) => {
          if (!cancelled) setRunningStatus(status.last ?? null);
        },
        () => {},
      );
    tick();
    const handle = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [running]);

  const selectedBytes = useMemo(() => {
    if (!plan) return 0;
    return plan.items
      .filter((item) => selected.has(item.entry_id))
      .reduce((sum, item) => sum + (item.size_bytes ?? 0), 0);
  }, [plan, selected]);

  const allSelected = Boolean(plan?.items.length) && selected.size === plan?.items.length;

  const toggleAll = () => {
    if (!plan || running) return;
    setSelected(allSelected ? new Set() : new Set(plan.items.map((item) => item.entry_id)));
  };

  const toggleOne = (entryId: string) => {
    if (running) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  };

  const run = async () => {
    if (running || selected.size === 0) return;
    setRunning(true);
    setRunningStatus(null);
    setErr(null);
    try {
      const entryIds = [...selected];
      if (isUpload) await webdavSync.publishSelected(entryIds);
      else await webdavSync.downloadSelected(entryIds);
      await onDone();
      await refreshPlan();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
      setRunningStatus(null);
    }
  };

  return (
    <ModalShell
      title={
        <>
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent">
            <TitleIcon size={18} />
          </div>
          <span>{title}</span>
        </>
      }
      onClose={onClose}
      wide
    >
      <div className="space-y-4">
        {/* Info header */}
        <div className="grid gap-2 sm:grid-cols-2 rounded-2xl border border-border/80 bg-bg-subtle/50 p-4 text-xs">
          <div className="space-y-0.5">
            <div className="text-fg-subtle text-[11px] font-semibold">{t.library.webdavRemoteUpdated}</div>
            <div className="font-medium text-fg-base">
              {plan?.remote_updated_at ? new Date(plan.remote_updated_at).toLocaleString() : t.common.unset}
            </div>
          </div>
          <div className="space-y-0.5">
            <div className="text-fg-subtle text-[11px] font-semibold">{t.library.webdavRemoteSnapshot}</div>
            <div className="font-mono text-xs text-fg-base truncate">
              {plan?.snapshot_id || t.common.unset}
            </div>
          </div>
        </div>

        {err && (
          <div className="flex items-start gap-2.5 rounded-xl bg-danger-subtle p-3 text-xs text-danger border border-danger/20">
            <AlertCircle size={15} className="shrink-0 mt-0.5" />
            <span>{err}</span>
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-12 gap-2 text-xs font-semibold text-fg-muted">
            <Loader2 size={16} className="animate-spin text-accent" />
            <span>{t.common.loading}</span>
          </div>
        )}

        {!loading && plan && (
          <>
            <div className="flex items-center justify-between">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-fg-base select-none">
                <input
                  type="checkbox"
                  checked={allSelected}
                  disabled={running || plan.items.length === 0}
                  onChange={toggleAll}
                  className="h-4 w-4 rounded border-border text-accent focus:ring-accent/20"
                />
                <span>
                  {t.library.webdavSelectedSummary(
                    selected.size,
                    plan.items.length,
                    formatBytes(selectedBytes),
                  )}
                </span>
              </label>
            </div>

            {running && (
              <div className="flex items-center gap-2 rounded-xl bg-accent/10 border border-accent/20 p-3 text-xs text-accent font-semibold animate-pulse">
                <Loader2 size={14} className="animate-spin" />
                <span>{webdavProgressText(runningStatus, mode, t)}</span>
              </div>
            )}

            <div className="max-h-[48vh] overflow-y-auto rounded-2xl border border-border/80 bg-bg-card divide-y divide-border/40">
              {plan.items.length === 0 ? (
                <div className="py-12 text-center text-xs font-medium text-fg-muted">
                  {isUpload
                    ? t.library.webdavNoUploadItems
                    : t.library.webdavNoDownloadItems}
                </div>
              ) : (
                plan.items.map((item) => (
                  <div
                    key={item.entry_id}
                    onClick={() => toggleOne(item.entry_id)}
                    className={cn(
                      "flex items-center justify-between px-4 py-3 text-xs transition-colors cursor-pointer select-none",
                      selected.has(item.entry_id)
                        ? "bg-bg-subtle/30 hover:bg-bg-subtle/60"
                        : "opacity-45 hover:opacity-75",
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0 pr-3">
                      <input
                        type="checkbox"
                        checked={selected.has(item.entry_id)}
                        disabled={running}
                        onChange={() => toggleOne(item.entry_id)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 rounded border-border text-accent focus:ring-accent/20"
                      />
                      <div className="min-w-0">
                        <p className="font-semibold text-fg-base truncate">{item.display_name}</p>
                        {item.folder_path && (
                          <p className="text-[11px] text-fg-subtle truncate">{item.folder_path}</p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 text-[11px] font-medium text-fg-muted">
                      <span>{formatBytes(item.size_bytes ?? 0)}</span>
                      <span className="rounded-lg bg-bg-muted px-2 py-0.5 text-[10px] font-bold text-fg-muted uppercase tracking-wider">
                        {t.library.webdavPlanReason(item.reason)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2.5 pt-3 border-t border-border/60">
          <button
            onClick={onClose}
            type="button"
            className="h-11 rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-muted hover:bg-bg-subtle hover:text-fg-base active:scale-95 transition-all shadow-xs"
          >
            {t.common.close}
          </button>
          <button
            onClick={run}
            disabled={running || selected.size === 0}
            type="button"
            className={cn(
              "h-11 rounded-xl px-5 text-xs font-semibold shadow-xs transition-all active:scale-95 flex items-center justify-center gap-2",
              running || selected.size === 0
                ? "cursor-not-allowed bg-bg-muted text-fg-subtle opacity-70"
                : "bg-accent text-accent-fg hover:bg-accent-hover shadow-indigo-500/20",
            )}
          >
            {running ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                <span>{t.dialogs.uploading}</span>
              </>
            ) : isUpload ? (
              t.library.webdavUploadSelected
            ) : (
              t.library.webdavDownloadSelected
            )}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

function ModalShell({
  title,
  onClose,
  children,
  wide,
}: {
  title: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4 animate-fade-in select-none"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "flex max-h-[calc(100vh-32px)] flex-col overflow-hidden rounded-3xl border border-border/80 bg-bg-card shadow-modal animate-scale-in",
          wide
            ? "w-[720px] max-w-[calc(100vw-32px)]"
            : "w-[440px] max-w-[calc(100vw-32px)]",
        )}
      >
        <header className="flex items-center justify-between border-b border-border/80 px-6 py-4 text-xs font-bold text-fg-base bg-bg-subtle/50">
          <div className="flex items-center gap-2.5 text-sm font-bold">{title}</div>
          <button
            onClick={onClose}
            title={t.common.close}
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-xl text-fg-muted hover:bg-bg-muted hover:text-fg-base active:scale-95 transition-all"
          >
            <X size={16} />
          </button>
        </header>
        <div className="overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  );
}

function extensionForFile(file: File): string {
  const parts = file.name.split(".");
  return parts.length > 1 ? `.${parts.pop()!.toLowerCase()}` : "";
}

function categoryForFile(file: File): UploadCategory {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (["pdf"].includes(ext)) return "pdfs";
  if (["md", "markdown", "txt", "rtf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "epub"].includes(ext)) {
    return "documents";
  }
  if (["png", "jpg", "jpeg", "webp", "gif", "svg", "heic", "tiff"].includes(ext)) {
    return "images";
  }
  if (["zip", "tar", "gz", "7z", "rar"].includes(ext)) {
    return "archives";
  }
  if (["mp3", "wav", "flac", "ogg", "m4a"].includes(ext)) {
    return "audio";
  }
  if (["mp4", "mov", "avi", "mkv", "webm"].includes(ext)) {
    return "videos";
  }
  return "unknown";
}

async function walkEntry(
  entry: FileSystemEntry,
  parentDirs: string[],
  out: UploadItem[],
): Promise<void> {
  if ((entry as FileSystemFileEntry).isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry);
    out.push({
      file,
      relDirs: parentDirs,
      loaded: 0,
      selected: DEFAULT_INCLUDED_CATEGORIES.includes(categoryForFile(file)),
      status: "queued",
    });
    return;
  }
  if ((entry as FileSystemDirectoryEntry).isDirectory) {
    const dir = entry as FileSystemDirectoryEntry;
    const reader = dir.createReader();
    const children: FileSystemEntry[] = [];
    while (true) {
      const chunk = await new Promise<FileSystemEntry[]>((res, rej) =>
        reader.readEntries((r) => res(r), (e) => rej(e)),
      );
      if (chunk.length === 0) break;
      children.push(...chunk);
    }
    const nextParents = [...parentDirs, dir.name];
    for (const child of children) {
      await walkEntry(child, nextParents, out);
    }
  }
}

function fileFromEntry(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function mkdirP(
  cache: Map<string, string | null>,
  relDirs: string[],
): Promise<string | null> {
  if (relDirs.length === 0) return cache.get("") ?? null;
  let key = "";
  let parentId: string | null = cache.get("") ?? null;
  for (const seg of relDirs) {
    key = key ? `${key}/${seg}` : seg;
    if (cache.has(key)) {
      parentId = cache.get(key)!;
      continue;
    }
    parentId = await ensureFolder(seg, parentId);
    cache.set(key, parentId);
  }
  return parentId;
}

async function ensureFolder(name: string, parentId: string | null): Promise<string> {
  try {
    const f = await foldersApi.create(name, parentId);
    return f.id;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      const body = typeof e.body === "object" && e.body && "detail" in e.body
        ? (e.body.detail as { existing_id?: string } | undefined)
        : undefined;
      if (body?.existing_id) return body.existing_id;
      const listing = await foldersApi.list(parentId ?? null);
      const hit = listing.folders.find((f) => f.name === name);
      if (hit) return hit.id;
    }
    throw e;
  }
}

function webdavProgressText(
  last: WebDavSyncLast | null,
  mode: "upload" | "download",
  t: I18nStrings,
): string {
  if (!last) return t.common.loading;
  if (last.phase) return t.library.webdavSyncPhase(last.phase);
  if (mode === "upload") {
    return t.library.webdavProgressBlobs(
      last.processed_blobs ?? 0,
      last.total_blobs ?? 0,
      last.uploaded_blobs ?? 0,
      last.skipped_blobs ?? 0,
    );
  }
  return t.library.webdavProgressMetadata(
    last.last_download?.downloaded_files ?? 0,
    last.last_download?.requested_files ?? 0,
  );
}
