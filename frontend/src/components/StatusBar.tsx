import { useEffect, useRef, useState } from "react";
import { Activity, Wifi, WifiOff, HardDrive } from "lucide-react";

import { health, tasks } from "@/api/client";
import { ActivityPopover } from "@/components/ActivityPopover";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export function StatusBar() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [storage, setStorage] = useState<string>("");
  const [busy, setBusy] = useState({ running: 0, pending: 0 });
  const [popoverOpen, setPopoverOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const pollMs = usePrefs((s) => s.statusPollMs);
  const { t } = useI18n();

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const h = await health();
        if (cancelled) return;
        setOnline(true);
        setStorage(h.storage_backend);
      } catch {
        if (!cancelled) setOnline(false);
      }
      try {
        const c = await tasks.runningCount();
        if (!cancelled) setBusy(c);
      } catch {
        /* keep last value */
      }
    }

    tick();
    const id = window.setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  // Click-outside to close popover
  useEffect(() => {
    if (!popoverOpen) return;
    function onDown(ev: MouseEvent) {
      if (!popoverRef.current) return;
      if (!popoverRef.current.contains(ev.target as Node)) {
        setPopoverOpen(false);
      }
    }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [popoverOpen]);

  const totalBusy = busy.running + busy.pending;

  return (
    <footer className="relative flex h-8.5 shrink-0 items-center justify-between border-t border-border/70 bg-bg-subtle/95 px-4 text-xs text-fg-muted select-none z-20">
      <div className="flex items-center gap-3.5">
        {/* Network & Backend Status */}
        <div
          className={cn(
            "flex items-center gap-2 font-medium transition-colors",
            online === false ? "text-danger" : online ? "text-fg-muted" : "text-fg-subtle",
          )}
        >
          <span className="flex items-center gap-1.5">
            {online === false ? (
              <WifiOff size={13} className="text-danger" />
            ) : (
              <Wifi size={13} className={online ? "text-emerald-500" : "text-warning"} />
            )}
            <span className="relative flex h-2 w-2">
              {online === true ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
                </>
              ) : online === false ? (
                <span className="relative inline-flex h-2 w-2 rounded-full bg-danger"></span>
              ) : (
                <span className="relative inline-flex h-2 w-2 rounded-full bg-warning animate-pulse"></span>
              )}
            </span>
          </span>
          <span className="text-[11.5px]">
            {online === null
              ? t.status.connecting
              : online
                ? t.status.connected(storage)
                : t.status.backendOffline}
          </span>
        </div>

        {/* Storage Badge */}
        {storage && (
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-bg-muted/80 text-[11px] font-mono text-fg-subtle border border-border/50">
            <HardDrive size={11.5} />
            <span>{storage}</span>
          </div>
        )}
      </div>

      <div ref={popoverRef}>
        <button
          onClick={() => setPopoverOpen((o) => !o)}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold transition-all duration-150 active:scale-95",
            "hover:bg-bg-muted hover:text-fg-base",
            popoverOpen && "bg-bg-muted text-fg-base ring-1 ring-border/80",
            totalBusy > 0 && "text-accent",
          )}
          title={t.status.showActivity}
          type="button"
        >
          <Activity
            size={13}
            className={cn(totalBusy > 0 && "text-accent animate-pulse-soft")}
          />
          {totalBusy > 0 ? (
            <span className="flex items-center gap-1.5">
              <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-accent-fg">
                {totalBusy}
              </span>
              <span className="text-[11.5px]">{t.status.busy(busy.running, busy.pending)}</span>
            </span>
          ) : (
            <span className="text-[11.5px] font-medium">{t.status.idle}</span>
          )}
        </button>
        <ActivityPopover open={popoverOpen} pollMs={pollMs} />
      </div>
    </footer>
  );
}
