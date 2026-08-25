import { useCallback, useEffect, useState } from "react";
import { Plus, MessageSquare, Loader2, Lock, Trash2, MessagesSquare } from "lucide-react";

import { sessions as sessionsApi } from "@/api/client";
import type { SessionListEntry } from "@/types/api";
import { cn } from "@/lib/utils";
import { useI18n, type I18nStrings } from "@/lib/i18n";

interface Props {
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNewChat: () => void;
  refreshSignal: number;
}

export function SessionList({
  activeSessionId,
  onSelect,
  onNewChat,
  refreshSignal,
}: Props) {
  const [entries, setEntries] = useState<SessionListEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { t, localeTag } = useI18n();

  useEffect(() => {
    let cancelled = false;
    sessionsApi
      .list(50)
      .then((r) => {
        if (!cancelled) setEntries(r.sessions);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  const handleDelete = useCallback(
    async (entry: SessionListEntry) => {
      const label = entry.preview ? `"${entry.preview.slice(0, 60)}"` : t.common.emptyName;
      if (!confirm(t.chat.deleteConfirm(label))) return;

      setDeletingId(entry.session_id);
      setErr(null);
      try {
        await sessionsApi.delete(entry.session_id);
        setEntries((prev) =>
          prev ? prev.filter((s) => s.session_id !== entry.session_id) : prev,
        );
        if (entry.session_id === activeSessionId) onNewChat();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setDeletingId(null);
      }
    },
    [activeSessionId, onNewChat, t],
  );

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border/80 bg-bg-subtle/80 select-none">
      {/* New Chat Button — Apple HIG 44px standard, prominent, high aesthetic */}
      <div className="p-3.5 border-b border-border/60">
        <button
          onClick={onNewChat}
          className="group relative flex h-11 w-full items-center justify-center gap-2.5 rounded-xl bg-accent px-4 text-sm font-semibold text-accent-fg shadow-xs transition-all duration-150 hover:bg-accent-hover active:scale-[0.98]"
          type="button"
        >
          <Plus size={16} strokeWidth={2.5} className="transition-transform group-hover:rotate-90 duration-200" />
          <span>{t.chat.newChat}</span>
        </button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-2.5 py-2.5 space-y-1">
        {entries === null && !err && (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-fg-subtle">
            <Loader2 size={14} className="animate-spin text-accent" />
            <span>{t.common.loading}</span>
          </div>
        )}
        {err && (
          <div className="m-1 rounded-xl border border-danger/30 bg-danger-subtle/80 p-3 text-xs text-danger">
            {err}
          </div>
        )}
        {entries && entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-14 text-center text-fg-subtle gap-2.5 px-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-bg-muted/80 text-fg-subtle border border-border/60">
              <MessagesSquare size={20} />
            </div>
            <p className="text-xs font-semibold text-fg-muted">{t.chat.noSessions}</p>
          </div>
        )}
        {entries &&
          entries.map((s) => (
            <SessionRow
              key={s.session_id}
              entry={s}
              active={s.session_id === activeSessionId}
              deleting={deletingId === s.session_id}
              onClick={() => onSelect(s.session_id)}
              onDelete={() => handleDelete(s)}
              t={t}
              localeTag={localeTag}
            />
          ))}
      </div>
    </aside>
  );
}

function SessionRow({
  entry,
  active,
  deleting,
  onClick,
  onDelete,
  t,
  localeTag,
}: {
  entry: SessionListEntry;
  active: boolean;
  deleting: boolean;
  onClick: () => void;
  onDelete: () => void;
  t: I18nStrings;
  localeTag: string;
}) {
  const closed = entry.ended_at !== null;
  const preview = entry.preview || t.common.emptyName;
  const when = entry.started_at ? formatRelative(entry.started_at, t, localeTag) : "";

  return (
    <div
      className={cn(
        "group relative flex min-h-[46px] items-center gap-2.5 rounded-xl px-3 py-2.5 text-xs transition-all duration-150",
        active
          ? "bg-bg-elevated text-fg-base shadow-xs ring-1 ring-border/90"
          : "text-fg-muted hover:bg-bg-muted/60 hover:text-fg-base",
      )}
    >
      {/* Active Indicator Bar */}
      {active && (
        <span className="absolute left-1 top-1/2 -translate-y-1/2 h-5 w-1 rounded-full bg-accent" />
      )}

      <button
        onClick={onClick}
        className="flex min-w-0 flex-1 items-start gap-2.5 text-left"
        title={preview}
        type="button"
      >
        <MessageSquare
          size={14}
          strokeWidth={active ? 2.2 : 1.8}
          className={cn(
            "mt-0.5 shrink-0 transition-colors",
            active ? "text-accent" : "text-fg-subtle group-hover:text-fg-muted",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className={cn("truncate font-semibold leading-snug text-xs", active ? "text-fg-base" : "text-fg-base/85")}>
              {preview}
            </span>
            {closed && <Lock size={10} className="shrink-0 text-fg-subtle opacity-70" />}
          </div>
          <div className="mt-0.75 flex items-center gap-1.5 text-[10.5px] text-fg-subtle font-normal">
            <span>{when}</span>
            <span>·</span>
            <span>{t.chat.turn(entry.turn_count)}</span>
          </div>
        </div>
      </button>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        disabled={deleting}
        title={t.chat.deleteSessionTitle}
        aria-label={t.chat.deleteSessionTitle}
        type="button"
        className={cn(
          "flex h-7 w-7 items-center justify-center shrink-0 rounded-lg text-fg-subtle transition-all duration-150",
          "hover:bg-danger-subtle hover:text-danger active:scale-95",
          "opacity-0 group-hover:opacity-100 focus:opacity-100",
          deleting && "opacity-100",
        )}
      >
        {deleting ? (
          <Loader2 size={13} className="animate-spin text-danger" />
        ) : (
          <Trash2 size={13} />
        )}
      </button>
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
