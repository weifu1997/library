/** Theme store (light/dark/system) persisted to localStorage.
 *  Mirrors the user's OS preference by default; a manual toggle
 *  overrides until the user clicks "system" again. */
import { create } from "zustand";

type ThemeMode = "light" | "dark" | "system";

interface ThemeState {
  mode: ThemeMode;
  effective: "light" | "dark";
  setMode: (m: ThemeMode) => void;
  init: () => () => void;
}

const STORAGE_KEY = "library.theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia
    && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(mode: ThemeMode): "light" | "dark" {
  const effective: "light" | "dark" =
    mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", effective === "dark");
  }
  return effective;
}

function readStoredMode(): ThemeMode {
  try {
    if (typeof localStorage === "undefined") return "system";
    const raw = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
  } catch {
    // storage unavailable (sandboxed iframe / strict private mode) — default.
    return "system";
  }
}

export const useTheme = create<ThemeState>((set, get) => ({
  mode: readStoredMode(),
  effective: "light",
  setMode: (m) => {
    try {
      if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEY, m);
    } catch {
      /* persist failure must not break the in-memory theme toggle */
    }
    set({ mode: m, effective: applyTheme(m) });
  },
  init: () => {
    set({ effective: applyTheme(get().mode) });
    if (typeof window === "undefined" || !window.matchMedia) return () => {};
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (get().mode === "system") {
        set({ effective: applyTheme("system") });
      }
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  },
}));
