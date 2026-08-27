import { useEffect, useRef, useState } from "react";
import { Library, RefreshCw } from "lucide-react";

import {
  clearBaseUrlOverride,
  getBaseUrlOverride,
  health,
} from "@/api/client";
import { useI18n } from "@/lib/i18n";

const POLL_INTERVAL_MS = 300;
const PER_ATTEMPT_TIMEOUT_MS = 1500;
const STALE_THRESHOLD_MS = 8000;

interface Props {
  children: React.ReactNode;
}

export function BackendGate({ children }: Props) {
  const [ready, setReady] = useState(false);
  const [waitedMs, setWaitedMs] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const loggedFirstFailure = useRef(false);
  const loggedStale = useRef(false);
  const { t } = useI18n();

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();

    (async () => {
      while (!cancelled) {
        const attempt = withTimeout(health(), PER_ATTEMPT_TIMEOUT_MS);
        try {
          await attempt;
          if (!cancelled) setReady(true);
          return;
        } catch (e: unknown) {
          if (cancelled) return;
          const message = e instanceof Error ? e.message : String(e);
          const elapsed = Date.now() - startedAt;
          setLastError(message);
          setWaitedMs(elapsed);
          if (!loggedFirstFailure.current) {
            loggedFirstFailure.current = true;
            console.warn("backend health check failed", {
              waitedMs: elapsed,
              error: message,
            });
          }
          if (elapsed >= STALE_THRESHOLD_MS && !loggedStale.current) {
            loggedStale.current = true;
            console.error("backend health check still failing", {
              waitedMs: elapsed,
              error: message,
            });
          }
          await sleep(POLL_INTERVAL_MS);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [retryNonce]);

  if (ready) return <>{children}</>;

  const stale = waitedMs >= STALE_THRESHOLD_MS;
  const baseUrlOverride = getBaseUrlOverride();
  return (
    <div className="flex h-full w-full items-center justify-center bg-bg-base px-4 text-fg-base select-none">
      <div className="w-full max-w-sm rounded-2xl border border-border/80 bg-bg-card/95 p-7 shadow-elevated text-center backdrop-blur-xl animate-scale-in">
        {/* Animated Brand Logo */}
        <div className="relative mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-500/25 ring-1 ring-white/25">
          <Library size={28} strokeWidth={2.2} />
          <span className="absolute -inset-1 rounded-2xl bg-indigo-500/20 blur-md animate-pulse"></span>
        </div>

        <h3 className="text-sm font-semibold tracking-tight text-fg-base">{t.backend.starting}</h3>
        {!stale ? (
          <p className="mt-1 text-xs text-fg-subtle">
            {t.backend.waiting}
          </p>
        ) : (
          <div className="mt-3.5 space-y-2 text-xs text-fg-subtle text-left">
            <p className="text-warning font-medium">
              {t.backend.slow(Math.round(waitedMs / 1000))}
            </p>
            <p className="text-[11.5px]">
              {t.backend.startBackend}
            </p>
            {lastError && (
              <p className="font-mono text-[10.5px] rounded bg-bg-muted p-2 text-fg-muted border border-border/60">{lastError}</p>
            )}
            {baseUrlOverride && (
              <div className="mt-3 rounded-lg border border-warning/30 bg-warning-subtle/80 p-3 text-left">
                <p className="font-medium text-warning text-xs">{t.backend.customBaseTitle}</p>
                <p className="mt-1 break-all font-mono text-[10px] text-fg-muted">{baseUrlOverride}</p>
                <p className="mt-1.5 text-[11px] text-fg-muted">{t.backend.customBaseBody}</p>
                <button
                  type="button"
                  onClick={() => {
                    clearBaseUrlOverride();
                    setWaitedMs(0);
                    setLastError(null);
                    loggedFirstFailure.current = false;
                    loggedStale.current = false;
                    setRetryNonce((n) => n + 1);
                  }}
                  className="mt-2.5 inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg hover:bg-accent-hover transition-colors"
                >
                  {t.backend.useDefault}
                </button>
              </div>
            )}
          </div>
        )}

        <div className="mt-5 flex justify-center">
          <button
            type="button"
            onClick={() => {
              setWaitedMs(0);
              setLastError(null);
              loggedFirstFailure.current = false;
              loggedStale.current = false;
              setRetryNonce((n) => n + 1);
            }}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-xs font-semibold text-accent-fg shadow-sm transition-all hover:bg-accent-hover active:scale-95"
          >
            <RefreshCw size={13} />
            {t.backend.retry}
          </button>
        </div>
      </div>
    </div>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}
