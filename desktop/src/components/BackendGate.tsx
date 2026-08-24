import { useEffect, useRef, useState } from "react";
import { Library, RefreshCw, LogOut, AlertTriangle } from "lucide-react";

import {
  clearBaseUrlOverride,
  getBaseUrlOverride,
  health,
  resetResolvedBaseUrl,
  resolveTauriBaseUrl,
} from "@/api/client";
import { useI18n } from "@/lib/i18n";
import { frontendLog, getTauriLogDir } from "@/lib/frontendLog";

const POLL_INTERVAL_MS = 300;
const PER_ATTEMPT_TIMEOUT_MS = 1500;
const STALE_THRESHOLD_MS = 8000;

interface Props {
  children: React.ReactNode;
}

interface BackendStatusInfo {
  state: string;
  message: string | null;
}

function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(
    (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ ||
      (window as unknown as { __TAURI__?: unknown }).__TAURI__,
  );
}

async function fetchBackendStatus(): Promise<BackendStatusInfo | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<BackendStatusInfo>("backend_status");
  } catch {
    return null;
  }
}

export function BackendGate({ children }: Props) {
  const [ready, setReady] = useState(false);
  const [waitedMs, setWaitedMs] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const [fatal, setFatal] = useState<BackendStatusInfo | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const [logDir, setLogDir] = useState("~/LibraryData/logs");
  const loggedFirstFailure = useRef(false);
  const loggedStale = useRef(false);
  const { t } = useI18n();

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();

    (async () => {
      await resolveTauriBaseUrl();
      const dir = await getTauriLogDir();
      if (!cancelled) setLogDir(dir);

      while (!cancelled) {
        const attempt = withTimeout(health(), PER_ATTEMPT_TIMEOUT_MS);
        try {
          await attempt;
          frontendLog("info", "backend health check passed", {
            waitedMs: Date.now() - startedAt,
          });
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
            frontendLog("warn", "backend health check failed", {
              waitedMs: elapsed,
              error: message,
            });
          }

          const status = await fetchBackendStatus();
          if (cancelled) return;
          if (status && (status.state === "error" || status.state === "exited")) {
            frontendLog("error", "backend startup failed", {
              state: status.state,
              message: status.message,
            });
            setFatal(status);
            return;
          }
          if (elapsed >= STALE_THRESHOLD_MS && !loggedStale.current) {
            loggedStale.current = true;
            frontendLog("error", "backend health check still failing", {
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

  if (fatal) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg-base px-4 text-fg-base select-none">
        <div className="w-full max-w-md rounded-2xl border border-danger/30 bg-bg-card p-6 shadow-modal backdrop-blur-xl animate-scale-in text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-danger-subtle text-danger mb-4 ring-1 ring-danger/30">
            <AlertTriangle size={24} />
          </div>
          <h2 className="text-base font-semibold text-danger">{t.backend.failedTitle}</h2>
          <div className="mt-3 space-y-2.5 text-xs text-fg-muted text-left">
            <p>{t.backend.failedBody}</p>
            {fatal.message && (
              <p className="break-all rounded-lg border border-border bg-bg-muted p-2.5 font-mono text-[11px] text-fg-base">
                {fatal.message}
              </p>
            )}
            <p className="text-[11.5px]">
              {t.backend.failedLogHint}{" "}
              <span className="break-all font-mono font-medium text-fg-base">{logDir}</span>
            </p>
          </div>
          <div className="mt-5 flex justify-center gap-2.5">
            <button
              type="button"
              onClick={() => {
                setFatal(null);
                setWaitedMs(0);
                setLastError(null);
                loggedFirstFailure.current = false;
                loggedStale.current = false;
                void (async () => {
                  try {
                    const { invoke } = await import("@tauri-apps/api/core");
                    await invoke("restart_backend");
                  } catch {
                    /* fallback */
                  }
                  resetResolvedBaseUrl();
                  setRetryNonce((n) => n + 1);
                })();
              }}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-xs font-semibold text-accent-fg shadow-sm transition-all hover:bg-accent-hover active:scale-95"
            >
              <RefreshCw size={13} />
              {t.backend.retry}
            </button>
            <button
              type="button"
              onClick={() => {
                void (async () => {
                  try {
                    const { invoke } = await import("@tauri-apps/api/core");
                    await invoke("quit_app");
                  } catch {
                    window.close();
                  }
                })();
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg-base px-4 py-2 text-xs font-medium text-fg-muted hover:bg-bg-muted hover:text-fg-base transition-colors"
            >
              <LogOut size={13} />
              {t.backend.quit}
            </button>
          </div>
        </div>
      </div>
    );
  }

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
              {t.backend.checkLog}{" "}
              <span className="break-all font-mono font-medium text-fg-base">{logDir}</span>
            </p>
            {lastError && (
              <p className="font-mono text-[10.5px] rounded bg-bg-muted p-2 text-fg-muted border border-border/60">{lastError}</p>
            )}
            {isTauri() && baseUrlOverride && (
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
                  {t.backend.useBundled}
                </button>
              </div>
            )}
          </div>
        )}

        <div className="mt-5 flex justify-center">
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-bg-muted">
            <div className="h-full w-full bg-indigo-500 animate-[shimmer_1.5s_infinite_linear] bg-gradient-to-r from-indigo-500 via-indigo-300 to-indigo-500 bg-[length:200%_100%]"></div>
          </div>
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
