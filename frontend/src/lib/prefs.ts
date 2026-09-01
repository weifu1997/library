/** User preferences persisted to localStorage.
 *
 *  Centralised so other components (StatusBar refresh cadence, sidebar
 *  layout) can subscribe instead of each reading raw localStorage with
 *  their own keys. */
import { create } from "zustand";

export type LanguagePreference = "auto" | "en" | "zh";

interface PrefsState {
  /** StatusBar polling interval in ms; clamped to [1000, 60000]. */
  statusPollMs: number;
  /** Auto-collapse sidebar on small windows. */
  compactSidebar: boolean;
  /** UI language. auto follows navigator.language. */
  language: LanguagePreference;

  setStatusPollMs: (v: number) => void;
  setCompactSidebar: (v: boolean) => void;
  setLanguage: (v: LanguagePreference) => void;
}

const KEY_POLL = "library.prefs.status_poll_ms";
const KEY_COMPACT = "library.prefs.compact_sidebar";
const KEY_LANGUAGE = "library.prefs.language";

/** Read a storage key, tolerating environments where even property access
 *  on `localStorage` throws (sandboxed iframes, strict private modes). */
function safeGet(key: string): string | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Best-effort write. A failed persist must not break the in-memory state —
 *  the caller sets the store after this regardless. */
function safeSet(key: string, value: string): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — preference still applies for this session */
  }
}

function readPollMs(): number {
  const raw = safeGet(KEY_POLL);
  const n = raw ? parseInt(raw, 10) : NaN;
  if (!Number.isFinite(n)) return 4000;
  return Math.min(60000, Math.max(1000, n));
}

function readCompact(): boolean {
  return safeGet(KEY_COMPACT) === "1";
}

function readLanguage(): LanguagePreference {
  const raw = safeGet(KEY_LANGUAGE);
  return raw === "en" || raw === "zh" || raw === "auto" ? raw : "auto";
}

export const usePrefs = create<PrefsState>((set) => ({
  statusPollMs: readPollMs(),
  compactSidebar: readCompact(),
  language: readLanguage(),
  setStatusPollMs: (v) => {
    const clamped = Math.min(60000, Math.max(1000, Math.round(v)));
    safeSet(KEY_POLL, String(clamped));
    set({ statusPollMs: clamped });
  },
  setCompactSidebar: (v) => {
    safeSet(KEY_COMPACT, v ? "1" : "0");
    set({ compactSidebar: v });
  },
  setLanguage: (v) => {
    safeSet(KEY_LANGUAGE, v);
    set({ language: v });
  },
}));
