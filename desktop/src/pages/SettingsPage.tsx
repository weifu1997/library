/** Settings page — Linear / Apple HIG modern card design.
 *
 *  1. Quick Start: First-run setup checklist and onboarding status.
 *  2. Connection: API base URL (client-side, persisted to localStorage).
 *  3. WebDAV: Remote cloud synchronization & snapshot status.
 *  4. Preferences: Language, Theme, Conflict policies, Agent budgets.
 *  5. Retrieval: Vector recall, Semantic index, Document vision & Rerank.
 *  6. Server Status & LLM Profiles: Runtime telemetry & per-task model overlays.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Save,
  Sun,
  Moon,
  Monitor,
  RefreshCw,
  Sparkles,
  Network,
  Cloud,
  Sliders,
  Database,
  Server,
  Key,
  Cpu,
  Check,
  Layers,
} from "lucide-react";

import {
  clearBaseUrlOverride,
  probeBackendBaseUrl,
  setApiToken,
  setBaseUrl,
  getApiToken,
  settings as settingsApi,
  tasks,
  webdavSync,
} from "@/api/client";
import { LlmProfileEditor } from "@/components/LlmProfileEditor";
import { usePrefs, type LanguagePreference } from "@/lib/prefs";
import { useTheme } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { LlmSettings, OnConflict, ServerSettings, WebDavStatus } from "@/types/api";

const STORAGE_KEY = "library.api_base";

type ServerNumberField =
  | "agent_plan_max_tokens"
  | "agent_execute_max_tokens"
  | "agent_execute_max_turns"
  | "worker_batch_size"
  | "llm_ingest_concurrency"
  | "embedding_dimensions"
  | "embedding_batch_size"
  | "semantic_recall_limit"
  | "rerank_top_n"
  | "rerank_max_doc_chars"
  | "rerank_concurrency";

type ServerBooleanField =
  | "compression_enabled"
  | "semantic_recall_enabled"
  | "rerank_enabled"
  | "document_vision_enabled"
  | "worker_enabled";

type ServerStringField =
  | "embedding_provider"
  | "embedding_base_url"
  | "embedding_model"
  | "semantic_index_backend"
  | "rerank_base_url"
  | "rerank_model"
  | "evidence_selection";

type ServerSecretField = "embedding_api_key" | "rerank_api_key";

interface ServerCtx {
  server: ServerSettings | null;
  llm: LlmSettings | null;
  err: string | null;
  setLlm: (next: LlmSettings) => void;
  setDefaultConflict: (v: OnConflict) => Promise<void>;
  setServerNumber: (field: ServerNumberField, v: number) => Promise<void>;
  setServerBoolean: (field: ServerBooleanField, v: boolean) => Promise<void>;
  setServerString: (field: ServerStringField, v: string) => Promise<void>;
  setServerSecret: (field: ServerSecretField, v: string) => Promise<void>;
}

export type SettingsTab =
  | "quickstart"
  | "llm"
  | "connection"
  | "preferences"
  | "retrieval"
  | "server"
  | "all";

export function SettingsPage() {
  const ctx = useServerCtx();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as SettingsTab | null;
  const [activeTab, setActiveTab] = useState<SettingsTab>(() => {
    if (
      tabParam &&
      [
        "quickstart",
        "llm",
        "connection",
        "preferences",
        "retrieval",
        "server",
        "all",
      ].includes(tabParam)
    ) {
      return tabParam;
    }
    return "quickstart";
  });

  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
    if (tab === "quickstart") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      searchParams.set("tab", tab);
      setSearchParams(searchParams, { replace: true });
    }
  };

  const tabs: {
    id: SettingsTab;
    label: string;
    icon: React.ElementType;
  }[] = [
    { id: "quickstart", label: t.settings.tabQuickStart, icon: Sparkles },
    { id: "llm", label: t.settings.tabLlm, icon: Cpu },
    { id: "connection", label: t.settings.tabConnection, icon: Network },
    { id: "preferences", label: t.settings.tabPreferences, icon: Sliders },
    { id: "retrieval", label: t.settings.tabRetrieval, icon: Database },
    { id: "server", label: t.settings.tabServer, icon: Server },
    { id: "all", label: t.settings.tabAll, icon: Layers },
  ];

  return (
    <div className="h-full overflow-y-auto px-6 py-8 select-none">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Page Header */}
        <header className="flex flex-col gap-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-fg-base">
              {t.settings.title}
            </h1>
            <span className="rounded-full bg-accent/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent border border-accent/20">
              Settings
            </span>
          </div>
          <p className="text-xs text-fg-muted">
            {t.settings.serverSubtitle || "Configure connection, model providers, and system parameters."}
          </p>
        </header>

        {/* Sub-Buttons / Tab Navigation Bar — Apple HIG / Linear aesthetic, >= 44px min touch height */}
        <div className="sticky top-0 z-20 flex items-center gap-1.5 overflow-x-auto rounded-2xl border border-border/80 bg-bg-card/95 p-1.5 shadow-sm backdrop-blur-md no-scrollbar">
          {tabs.map((tab) => {
            const active = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl px-4 text-xs font-semibold transition-all duration-150 active:scale-95",
                  active
                    ? "bg-accent text-accent-fg shadow-xs font-bold"
                    : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/70",
                )}
              >
                <Icon
                  size={15}
                  strokeWidth={active ? 2.3 : 1.8}
                  className={cn(active ? "text-accent-fg" : "text-fg-subtle")}
                />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Panels */}
        <div className="space-y-6 animate-fade-in">
          {(activeTab === "quickstart" || activeTab === "all") && (
            <QuickStartSection ctx={ctx} />
          )}

          {(activeTab === "llm" || activeTab === "all") && (
            <LlmSection ctx={ctx} />
          )}

          {(activeTab === "connection" || activeTab === "all") && (
            <>
              <ConnectionSection />
              <WebDavSection initial={ctx.server?.webdav ?? null} />
            </>
          )}

          {(activeTab === "preferences" || activeTab === "all") && (
            <PreferencesSection ctx={ctx} />
          )}

          {(activeTab === "retrieval" || activeTab === "all") && (
            <RetrievalSection ctx={ctx} />
          )}

          {(activeTab === "server" || activeTab === "all") && (
            <ServerSection ctx={ctx} />
          )}
        </div>
      </div>
    </div>
  );
}

function useServerCtx(): ServerCtx {
  const [server, setServer] = useState<ServerSettings | null>(null);
  const [llm, setLlm] = useState<LlmSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, l] = await Promise.all([
          settingsApi.server(),
          settingsApi.llm(),
        ]);
        if (cancelled) return;
        setServer(s);
        setLlm(l);
        setErr(null);
      } catch (e: unknown) {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setDefaultConflict = async (v: OnConflict) => {
    if (!server || server.default_on_conflict === v) return;
    const prev = server;
    setServer({ ...server, default_on_conflict: v });
    try {
      await settingsApi.updateLlm({ default_on_conflict: v });
    } catch {
      setServer(prev);
    }
  };

  const setServerNumber = async (field: ServerNumberField, v: number) => {
    if (!server || server[field] === v) return;
    const prev = server;
    setServer({ ...server, [field]: v } as ServerSettings);
    try {
      await settingsApi.updateLlm({ [field]: v });
    } catch {
      setServer(prev);
    }
  };

  const setServerBoolean = async (field: ServerBooleanField, v: boolean) => {
    if (!server || server[field] === v) return;
    const prev = server;
    const next: ServerSettings = { ...server, [field]: v };
    if (field === "semantic_recall_enabled") {
      next.semantic_recall_configured = v && server.embedding_api_key_set;
    } else if (field === "rerank_enabled") {
      next.rerank_configured = v && server.rerank_api_key_set;
    } else if (field === "worker_enabled") {
      // Live start/stop happens server-side; the authoritative running
      // state (`worker_running`) comes back on the next server snapshot.
      next.worker_running = v;
    }
    setServer(next);
    try {
      await settingsApi.updateLlm({ [field]: v });
      // Sync worker_running (and any worker_error / effective value) back.
      if (field === "worker_enabled") {
        const fresh = await settingsApi.server();
        setServer(fresh);
      }
    } catch {
      setServer(prev);
    }
  };

  const setServerString = async (field: ServerStringField, v: string) => {
    const trimmed = v.trim();
    if (!server || !trimmed || server[field] === trimmed) return;
    const prev = server;
    setServer({ ...server, [field]: trimmed } as ServerSettings);
    try {
      await settingsApi.updateLlm({ [field]: trimmed });
    } catch {
      setServer(prev);
    }
  };

  const setServerSecret = async (field: ServerSecretField, v: string) => {
    const trimmed = v.trim();
    if (!server || !trimmed) return;
    const prev = server;
    const flag =
      field === "embedding_api_key"
        ? "embedding_api_key_set"
        : "rerank_api_key_set";
    const next: ServerSettings = { ...server, [flag]: true };
    if (field === "embedding_api_key") {
      next.semantic_recall_configured = server.semantic_recall_enabled;
    } else {
      next.rerank_configured = server.rerank_enabled;
    }
    setServer(next);
    try {
      await settingsApi.updateLlm({ [field]: trimmed });
    } catch {
      setServer(prev);
    }
  };

  return {
    server,
    llm,
    err,
    setLlm,
    setDefaultConflict,
    setServerNumber,
    setServerBoolean,
    setServerString,
    setServerSecret,
  };
}

// ---- First-run guide ------------------------------------------------------

function QuickStartSection({ ctx }: { ctx: ServerCtx }) {
  const { llm, err } = ctx;
  const { t } = useI18n();
  const missing = missingRequiredProfiles(llm);
  const ready = Boolean(llm && missing.length === 0);
  const statusText = err
    ? t.settings.guideStatusOffline
    : !llm
      ? t.settings.guideStatusLoading
      : ready
        ? t.settings.guideStatusReady
        : !llm.defaults.api_key_set && missing.length === 3
          ? t.settings.guideStatusDefaultMissing
          : t.settings.guideStatusMissingProfiles(missing.join(", "));

  return (
    <Section
      icon={Sparkles}
      title={t.settings.guideTitle}
      subtitle={t.settings.guideSubtitle}
    >
      <div className="space-y-4">
        <div
          className={cn(
            "flex items-start gap-3 rounded-2xl border p-4 text-xs transition-colors",
            ready
              ? "border-accent/30 bg-accent/10 text-fg-base"
              : "border-danger/25 bg-danger/10 text-fg-base",
          )}
        >
          {ready ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
          ) : (
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
          )}
          <div className="flex-1 font-semibold leading-relaxed">{statusText}</div>
        </div>

        <ol className="space-y-3 text-xs">
          <GuideStep index={1} title={t.settings.guideConfigureTitle}>
            <p>{t.settings.guideConfigureBody}</p>
            <p className="mt-1 text-[11px] text-fg-subtle">
              {t.settings.guideLocalModelPrefix}{" "}
              <code className="rounded-md bg-bg-base px-1.5 py-0.5 font-mono text-[11px] border border-border/70">openai-compatible</code>,{" "}
              <code className="rounded-md bg-bg-base px-1.5 py-0.5 font-mono text-[11px] border border-border/70">http://127.0.0.1:11434/v1</code>{" "}
              {t.common.or}{" "}
              <code className="rounded-md bg-bg-base px-1.5 py-0.5 font-mono text-[11px] border border-border/70">http://127.0.0.1:1234/v1</code>;
              {" "}{t.settings.guideLocalModelKey}
            </p>
          </GuideStep>
          <GuideStep index={2} title={t.settings.guideImportTitle}>
            <p>{t.settings.guideImportBody}</p>
          </GuideStep>
          <GuideStep index={3} title={t.settings.guideAskTitle}>
            <p>{t.settings.guideAskBody}</p>
          </GuideStep>
          <GuideStep index={4} title={t.settings.guideEmbeddingTitle}>
            <p>{t.settings.guideEmbeddingBody}</p>
          </GuideStep>
        </ol>
      </div>
    </Section>
  );
}

function GuideStep({
  index,
  title,
  children,
}: {
  index: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-3.5 rounded-xl border border-border/60 bg-bg-base/40 p-3.5">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-bold text-accent">
        {index}
      </span>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-fg-base text-xs">{title}</div>
        <div className="mt-1 text-fg-muted leading-relaxed text-[11.5px]">{children}</div>
      </div>
    </li>
  );
}

function missingRequiredProfiles(llm: LlmSettings | null): string[] {
  if (!llm) return [];
  return (["chat", "reflect", "ingest"] as const).filter(
    (profile) => !llm.profiles[profile]?.api_key_set,
  );
}

// ---- Connection ------------------------------------------------------------

function ConnectionSection() {
  const { t } = useI18n();
  const [base, setBase] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [token, setToken] = useState(() => getApiToken());
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const save = async () => {
    const v = base.trim().replace(/\/$/, "");
    setSaving(true);
    setSaveError(null);
    setSavedAt(null);
    try {
      if (v) {
        await probeBackendBaseUrl(v, token);
        localStorage.setItem(STORAGE_KEY, v);
        setBaseUrl(v);
      } else {
        clearBaseUrlOverride();
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setSaveError(t.settings.apiBaseValidationFailed(detail));
      return;
    } finally {
      setSaving(false);
    }
    setApiToken(token);
    setSavedAt(Date.now());
  };

  return (
    <Section
      icon={Network}
      title={t.settings.connectionTitle}
      subtitle={t.settings.connectionSubtitle}
    >
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-bold text-fg-base">
            {t.settings.apiBaseUrl}
          </label>
          <p className="mt-0.5 text-xs text-fg-subtle">
            {t.settings.apiBaseHelp}
            <span className="mx-1 font-mono text-[11px] text-accent">http://host:8000</span>
            {t.settings.apiBaseHelpTail}
          </p>
          <p className="mt-0.5 text-xs text-warning font-medium">{t.settings.apiBaseModelWarning}</p>
          <div className="mt-3 flex gap-2.5">
            <input
              value={base}
              onChange={(e) => setBase(e.target.value)}
              placeholder={t.settings.apiBasePlaceholder}
              className="h-11 flex-1 rounded-xl border border-border/80 bg-bg-base/70 px-3.5 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            />
            <button
              onClick={() => void save()}
              disabled={saving}
              className={cn(
                "inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-xs font-semibold text-accent-fg shadow-xs",
                "hover:bg-accent-hover active:scale-[0.98] disabled:opacity-50 transition-all shadow-indigo-500/20",
              )}
            >
              <Save size={14} /> {saving ? t.settings.apiBaseValidating : t.common.save}
            </button>
          </div>
        </div>

        <div className="border-t border-border/60 pt-4">
          <label className="block text-xs font-bold text-fg-base">
            {t.settings.apiToken}
          </label>
          <p className="mt-0.5 text-xs text-fg-subtle">{t.settings.apiTokenHelp}</p>
          <div className="relative mt-2.5">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-fg-subtle">
              <Key size={14} />
            </div>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              type="password"
              placeholder={t.settings.apiTokenPlaceholder}
              className="h-11 w-full rounded-xl border border-border/80 bg-bg-base/70 pl-10 pr-3.5 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            />
          </div>
        </div>

        {savedAt && (
          <p className="inline-flex items-center gap-1.5 text-xs text-accent font-semibold">
            <Check size={14} />
            {t.common.saved} · {new Date(savedAt).toLocaleTimeString()}
          </p>
        )}
        {saveError && (
          <div className="flex items-start gap-2.5 rounded-xl border border-danger/20 bg-danger/10 p-3 text-xs text-danger">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            <span>{saveError}</span>
          </div>
        )}
      </div>
    </Section>
  );
}

// ---- WebDAV sync -----------------------------------------------------------

function WebDavSection({ initial }: { initial: WebDavStatus | null }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<WebDavStatus | null>(initial);
  const [url, setUrl] = useState(initial?.url ?? "");
  const [username, setUsername] = useState(initial?.username ?? "");
  const [password, setPassword] = useState("");
  const [remotePath, setRemotePath] = useState(initial?.remote_path ?? "/library");
  const [autoSync, setAutoSync] = useState(Boolean(initial?.auto_sync_enabled));
  const [interval, setIntervalValue] = useState(String(initial?.auto_sync_interval_minutes ?? 60));
  const [busy, setBusy] = useState<"save" | "remote" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    webdavSync.status().then(
      (s) => {
        if (cancelled) return;
        setStatus(s);
        setUrl(s.url ?? "");
        setUsername(s.username ?? "");
        setRemotePath(s.remote_path || "/library");
        setAutoSync(Boolean(s.auto_sync_enabled));
        setIntervalValue(String(s.auto_sync_interval_minutes ?? 60));
      },
      () => {},
    );
    return () => { cancelled = true; };
  }, []);

  const refresh = async () => {
    const next = await webdavSync.status();
    setStatus(next);
    return next;
  };

  const save = async () => {
    setBusy("save");
    setMessage(null);
    setError(null);
    try {
      const patch: Record<string, string | number | boolean | null> = {
        webdav_url: url.trim() || null,
        webdav_username: username.trim() || null,
        webdav_remote_path: remotePath.trim() || "/library",
        webdav_auto_sync_enabled: autoSync,
        webdav_auto_sync_interval_minutes: parseInt(interval, 10) || 60,
      };
      if (password.trim()) patch.webdav_password = password.trim();
      const next = await webdavSync.updateConfig(patch);
      setStatus(next);
      setPassword("");
      setMessage(t.settings.webdavSaved);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const syncRemoteStatus = async () => {
    setBusy("remote");
    setMessage(null);
    setError(null);
    try {
      const result = await webdavSync.remoteStatus();
      await refresh();
      setMessage(t.settings.webdavRemoteStatusOk(result.status));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const last = status?.last;
  const lastUpload = last?.finished_at ? formatDateTime(last.finished_at) : t.common.unset;
  const lastRemoteCheck = last?.last_remote_check_at
    ? formatDateTime(last.last_remote_check_at)
    : t.common.unset;
  const remoteUpdated = last?.remote_updated_at
    ? formatDateTime(last.remote_updated_at)
    : t.common.unset;
  const remoteSnapshot = last?.remote_snapshot_id || t.common.unset;

  return (
    <Section
      icon={Cloud}
      title={t.settings.webdavTitle}
      subtitle={t.settings.webdavSubtitle}
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Row label={t.settings.webdavUrl}>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/dav"
                className="h-10 w-full sm:w-80 rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
              />
            </Row>
          </div>

          <Row label={t.settings.webdavRemotePath} hint={t.settings.webdavRemotePathHint}>
            <input
              value={remotePath}
              onChange={(e) => setRemotePath(e.target.value)}
              placeholder="/library"
              className="h-10 w-52 rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            />
          </Row>

          <Row label={t.settings.webdavUsername}>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              className="h-10 w-52 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            />
          </Row>

          <div className="sm:col-span-2">
            <Row
              label={t.settings.webdavPassword}
              hint={status?.password_set ? t.settings.webdavPasswordSet : t.settings.webdavPasswordHint}
            >
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={status?.password_set ? t.settings.webdavKeepPassword : "Password"}
                className="h-10 w-52 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
              />
            </Row>
          </div>

          <div className="sm:col-span-2">
            <Row label={t.settings.webdavAutoSync} hint={t.settings.webdavAutoSyncHint}>
              <div className="flex items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={autoSync}
                  onChange={(e) => setAutoSync(e.target.checked)}
                  className="h-4.5 w-4.5 rounded border-border text-accent accent-accent"
                />
                <input
                  type="number"
                  min={5}
                  max={10080}
                  value={interval}
                  onChange={(e) => setIntervalValue(e.target.value)}
                  className="h-10 w-24 rounded-xl border border-border/80 bg-bg-base/70 px-2.5 text-right font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
                />
                <span className="text-xs text-fg-subtle">{t.settings.webdavMinutes}</span>
              </div>
            </Row>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border/60 pt-4">
          <button
            onClick={save}
            disabled={busy !== null}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-xs font-semibold text-accent-fg shadow-xs hover:bg-accent-hover active:scale-[0.98] disabled:opacity-50 transition-all shadow-indigo-500/20"
          >
            <Save size={14} /> {busy === "save" ? t.settings.webdavSaving : t.common.save}
          </button>
          <button
            onClick={syncRemoteStatus}
            disabled={busy !== null || !status?.configured}
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-base hover:bg-bg-subtle active:scale-[0.98] disabled:opacity-50 transition-all shadow-xs"
          >
            {busy === "remote" && <RefreshCw size={14} className="animate-spin text-accent" />}
            {t.settings.webdavRemoteStatus}
          </button>
        </div>

        <div className="rounded-2xl border border-border/60 bg-bg-subtle/40 p-4 text-xs">
          <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2">
            <Kv k={t.settings.webdavConfigured} v={status?.configured ? t.common.yes : t.common.no} />
            <Kv k={t.settings.webdavLastRemoteCheck} v={lastRemoteCheck} />
            <Kv k={t.settings.webdavRemoteUpdated} v={remoteUpdated} />
            <Kv k={t.settings.webdavSnapshot} v={remoteSnapshot} mono />
            <Kv k={t.settings.webdavLastUpload} v={lastUpload} />
            {last?.last_download_at && (
              <Kv k={t.settings.webdavLastDownload} v={formatDateTime(last.last_download_at)} />
            )}
            {last?.remote_error && <Kv k={t.settings.webdavRemoteError} v={last.remote_error} />}
            {last?.error && <Kv k={t.settings.webdavLastError} v={last.error} />}
          </dl>
        </div>

        {message && <p className="text-xs text-accent font-semibold">{message}</p>}
        {error && <p className="text-xs text-danger font-medium">{error}</p>}
      </div>
    </Section>
  );
}

// ---- Preferences -----------------------------------------------------------

function PreferencesSection({ ctx }: { ctx: ServerCtx }) {
  const { mode, setMode } = useTheme();
  const prefs = usePrefs();
  const { t, language, setLanguage } = useI18n();
  const {
    server,
    setDefaultConflict,
    setServerNumber,
    setServerBoolean,
  } = ctx;

  return (
    <Section
      icon={Sliders}
      title={t.settings.preferencesTitle}
      subtitle={t.settings.preferencesSubtitle}
    >
      <div className="space-y-4 divide-y divide-border/60">
        <div className="pt-0">
          <Row label={t.settings.language} hint={t.settings.languageHint}>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as LanguagePreference)}
              className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs font-semibold focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            >
              <option value="auto">{t.locale.auto}</option>
              <option value="en">{t.locale.en}</option>
              <option value="zh">{t.locale.zh}</option>
            </select>
          </Row>
        </div>

        <div className="pt-4">
          <Row label={t.settings.theme}>
            <div className="grid grid-cols-3 gap-1 rounded-xl border border-border/80 bg-bg-base/80 p-1 shadow-xs min-w-[300px]">
              {(["light", "dark", "system"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  type="button"
                  className={cn(
                    "flex h-9 items-center justify-center gap-2 rounded-lg text-xs font-semibold transition-all active:scale-95",
                    mode === m
                      ? "bg-accent text-accent-fg shadow-xs font-bold"
                      : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/50",
                  )}
                >
                  {m === "light" && <Sun size={14} />}
                  {m === "dark" && <Moon size={14} />}
                  {m === "system" && <Monitor size={14} />}
                  <span>{t.theme[m]}</span>
                </button>
              ))}
            </div>
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.conflictPolicy}
            hint={t.settings.conflictHint}
          >
            <select
              value={server?.default_on_conflict ?? "rename"}
              disabled={!server}
              onChange={(e) => void setDefaultConflict(e.target.value as OnConflict)}
              className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs font-medium focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all disabled:opacity-50"
            >
              <option value="rename">{t.settings.conflictRename}</option>
              <option value="error">{t.settings.conflictError}</option>
              <option value="skip">{t.settings.conflictSkip}</option>
            </select>
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.agentTokenBudget}
            hint={t.settings.agentTokenBudgetHint}
          >
            <div className="flex items-center gap-2.5">
              <NumberInput
                value={server?.agent_plan_max_tokens}
                disabled={!server}
                min={1}
                max={200000}
                step={128}
                className="w-28"
                onCommit={(v) => setServerNumber("agent_plan_max_tokens", v)}
              />
              <span className="text-xs text-fg-subtle">/</span>
              <NumberInput
                value={server?.agent_execute_max_tokens}
                disabled={!server}
                min={1}
                max={200000}
                step={128}
                className="w-28"
                onCommit={(v) => setServerNumber("agent_execute_max_tokens", v)}
              />
            </div>
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.executeTurnBudget}
            hint={t.settings.executeTurnBudgetHint}
          >
            <NumberInput
              value={server?.agent_execute_max_turns}
              disabled={!server}
              min={3}
              max={100}
              step={1}
              className="w-24"
              onCommit={(v) => setServerNumber("agent_execute_max_turns", v)}
            />
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.compression}
            hint={t.settings.compressionHint}
          >
            <input
              type="checkbox"
              checked={Boolean(server?.compression_enabled)}
              disabled={!server}
              onChange={(e) => setServerBoolean("compression_enabled", e.target.checked)}
              className="h-4.5 w-4.5 rounded border-border text-accent accent-accent disabled:opacity-50"
            />
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.concurrentIngest}
            hint={t.settings.concurrentIngestHint}
          >
            <NumberInput
              value={server?.worker_batch_size}
              disabled={!server}
              min={1}
              max={32}
              step={1}
              className="w-24"
              onCommit={(v) => setServerNumber("worker_batch_size", v)}
            />
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.ingestLlmConcurrency}
            hint={t.settings.ingestLlmConcurrencyHint}
          >
            <NumberInput
              value={server?.llm_ingest_concurrency}
              disabled={!server}
              min={1}
              max={32}
              step={1}
              className="w-24"
              onCommit={(v) => setServerNumber("llm_ingest_concurrency", v)}
            />
          </Row>
        </div>

        <div className="pt-4">
          <Row
            label={t.settings.statusRefresh}
            hint={t.settings.statusRefreshHint}
          >
            <select
              value={prefs.statusPollMs}
              onChange={(e) => prefs.setStatusPollMs(parseInt(e.target.value, 10))}
              className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
            >
              <option value={2000}>2 s</option>
              <option value={4000}>4 s (default)</option>
              <option value={10000}>10 s</option>
              <option value={30000}>30 s</option>
              <option value={60000}>60 s</option>
            </select>
          </Row>
        </div>

        <div className="pt-4">
          <Row label={t.settings.compactSidebar} hint={t.settings.compactSidebarHint}>
            <input
              type="checkbox"
              checked={prefs.compactSidebar}
              onChange={(e) => prefs.setCompactSidebar(e.target.checked)}
              className="h-4.5 w-4.5 rounded border-border text-accent accent-accent"
            />
          </Row>
        </div>
      </div>
    </Section>
  );
}

// ---- Retrieval ------------------------------------------------------------

function RetrievalSection({ ctx }: { ctx: ServerCtx }) {
  const {
    server,
    setServerBoolean,
    setServerNumber,
    setServerString,
    setServerSecret,
  } = ctx;
  const { t } = useI18n();
  const [rebuildBusy, setRebuildBusy] = useState(false);
  const [rebuildMessage, setRebuildMessage] = useState<string | null>(null);
  const [rebuildError, setRebuildError] = useState<string | null>(null);

  if (!server) {
    return (
      <Section
        icon={Database}
        title={t.settings.retrievalTitle}
        subtitle={t.settings.retrievalSubtitle}
      >
        <p className="text-xs text-fg-subtle">{t.common.loading}</p>
      </Section>
    );
  }

  const rebuildSemanticIndex = async () => {
    setRebuildBusy(true);
    setRebuildMessage(null);
    setRebuildError(null);
    try {
      const result = await settingsApi.rebuildSemanticIndex();
      setRebuildMessage(t.settings.semanticRebuildQueued(result.task_id?.slice(0, 8) ?? ""));
    } catch (e: unknown) {
      setRebuildError(e instanceof Error ? e.message : String(e));
    } finally {
      setRebuildBusy(false);
    }
  };

  return (
    <Section
      icon={Database}
      title={t.settings.retrievalTitle}
      subtitle={t.settings.retrievalSubtitle}
    >
      <div className="space-y-6">
        {/* Vector Embedding group */}
        <div className="space-y-3.5">
          <div className="flex items-center gap-2 text-xs font-bold text-fg-base">
            <span className="h-2 w-2 rounded-full bg-accent" />
            {t.settings.embeddingGroup}
          </div>

          <div className="space-y-3.5 pl-4 border-l border-border/60">
            <Row label={t.settings.semanticRecall} hint={t.settings.semanticRecallHint}>
              <input
                type="checkbox"
                checked={server.semantic_recall_enabled}
                onChange={(e) => setServerBoolean("semantic_recall_enabled", e.target.checked)}
                className="h-4.5 w-4.5 rounded border-border text-accent accent-accent"
              />
            </Row>

            <Row label={t.settings.embeddingProvider}>
              <select
                value={server.embedding_provider}
                onChange={(e) => setServerString("embedding_provider", e.target.value)}
                className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
              >
                <option value="openai-compatible">openai-compatible</option>
                <option value="dashscope">dashscope</option>
              </select>
            </Row>

            <Row label={t.settings.embeddingApiKey} hint={t.llm.keepKeyHint}>
              <SecretInput
                configured={server.embedding_api_key_set}
                onCommit={(v) => setServerSecret("embedding_api_key", v)}
              />
            </Row>

            <Row label={t.settings.embeddingBaseUrl}>
              <TextInput
                value={server.embedding_base_url}
                className="w-72"
                onCommit={(v) => setServerString("embedding_base_url", v)}
              />
            </Row>

            <Row label={t.settings.embeddingModel}>
              <TextInput
                value={server.embedding_model}
                className="w-56"
                onCommit={(v) => setServerString("embedding_model", v)}
              />
            </Row>

            <Row label={t.settings.embeddingDimensions}>
              <NumberInput
                value={server.embedding_dimensions}
                min={1}
                max={8192}
                step={1}
                className="w-28"
                onCommit={(v) => setServerNumber("embedding_dimensions", v)}
              />
            </Row>

            <Row label={t.settings.embeddingBatchSize}>
              <NumberInput
                value={server.embedding_batch_size}
                min={1}
                max={10}
                step={1}
                className="w-24"
                onCommit={(v) => setServerNumber("embedding_batch_size", v)}
              />
            </Row>

            <Row label={t.settings.semanticRecallLimit}>
              <NumberInput
                value={server.semantic_recall_limit}
                min={1}
                max={1000}
                step={1}
                className="w-28"
                onCommit={(v) => setServerNumber("semantic_recall_limit", v)}
              />
            </Row>

            <Row label={t.settings.semanticIndexBackend}>
              <select
                value={server.semantic_index_backend}
                onChange={(e) => setServerString("semantic_index_backend", e.target.value)}
                className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
              >
                <option value="auto">auto</option>
                <option value="file">file</option>
                <option value="sqlite-vec">sqlite-vec</option>
              </select>
            </Row>

            <Row label={t.settings.semanticIndex} hint={t.settings.semanticIndexHint}>
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="rounded-xl border border-border/70 bg-bg-base/60 px-3 py-1.5 font-mono text-xs text-fg-muted">
                    {semanticIndexStatusLabel(server, t)}
                  </span>
                  <button
                    type="button"
                    disabled={!server.embedding_api_key_set || rebuildBusy}
                    onClick={rebuildSemanticIndex}
                    className="inline-flex h-10 items-center gap-2 rounded-xl border border-border/80 bg-bg-card px-3.5 text-xs font-semibold text-fg-base hover:bg-bg-subtle active:scale-[0.98] disabled:opacity-50 transition-all shadow-xs"
                    title={server.embedding_api_key_set ? t.settings.rebuildSemanticIndex : t.settings.semanticRebuildNoKey}
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5", rebuildBusy && "animate-spin text-accent")} />
                    {t.settings.rebuildSemanticIndex}
                  </button>
                </div>
                {rebuildMessage && <p className="text-xs text-accent font-medium">{rebuildMessage}</p>}
                {rebuildError && <p className="text-xs text-danger font-medium">{rebuildError}</p>}
              </div>
            </Row>
          </div>
        </div>

        {/* Vision & Multimodal group */}
        <div className="space-y-3.5 border-t border-border/60 pt-5">
          <div className="flex items-center gap-2 text-xs font-bold text-fg-base">
            <span className="h-2 w-2 rounded-full bg-accent" />
            {t.settings.documentVisionGroup}
          </div>

          <div className="space-y-3.5 pl-4 border-l border-border/60">
            <Row label={t.settings.documentVisionEnabled} hint={t.settings.documentVisionEnabledHint}>
              <input
                type="checkbox"
                checked={server.document_vision_enabled}
                onChange={(e) => setServerBoolean("document_vision_enabled", e.target.checked)}
                className="h-4.5 w-4.5 rounded border-border text-accent accent-accent"
              />
            </Row>
          </div>
        </div>

        {/* Rerank group */}
        <div className="space-y-3.5 border-t border-border/60 pt-5">
          <div className="flex items-center gap-2 text-xs font-bold text-fg-base">
            <span className="h-2 w-2 rounded-full bg-accent" />
            {t.settings.rerankGroup}
          </div>

          <div className="space-y-3.5 pl-4 border-l border-border/60">
            <Row label={t.settings.rerankEnabled} hint={t.settings.rerankEnabledHint}>
              <input
                type="checkbox"
                checked={server.rerank_enabled}
                onChange={(e) => setServerBoolean("rerank_enabled", e.target.checked)}
                className="h-4.5 w-4.5 rounded border-border text-accent accent-accent"
              />
            </Row>

            <Row label={t.settings.rerankApiKey} hint={t.llm.keepKeyHint}>
              <SecretInput
                configured={server.rerank_api_key_set}
                onCommit={(v) => setServerSecret("rerank_api_key", v)}
              />
            </Row>

            <Row label={t.settings.rerankBaseUrl}>
              <TextInput
                value={server.rerank_base_url}
                className="w-72"
                onCommit={(v) => setServerString("rerank_base_url", v)}
              />
            </Row>

            <Row label={t.settings.rerankModel}>
              <TextInput
                value={server.rerank_model}
                className="w-56"
                onCommit={(v) => setServerString("rerank_model", v)}
              />
            </Row>

            <Row label={t.settings.rerankTopN}>
              <NumberInput
                value={server.rerank_top_n}
                min={1}
                max={1000}
                step={1}
                className="w-28"
                onCommit={(v) => setServerNumber("rerank_top_n", v)}
              />
            </Row>

            <Row label={t.settings.rerankMaxDocChars}>
              <NumberInput
                value={server.rerank_max_doc_chars}
                min={1}
                max={200000}
                step={100}
                className="w-32"
                onCommit={(v) => setServerNumber("rerank_max_doc_chars", v)}
              />
            </Row>

            <Row label={t.settings.rerankConcurrency}>
              <NumberInput
                value={server.rerank_concurrency}
                min={1}
                max={64}
                step={1}
                className="w-24"
                onCommit={(v) => setServerNumber("rerank_concurrency", v)}
              />
            </Row>

            <Row label={t.settings.evidenceSelection} hint={t.settings.evidenceSelectionHint}>
              <select
                value={server.evidence_selection}
                onChange={(e) => setServerString("evidence_selection", e.target.value)}
                className="h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
              >
                <option value="quota">quota</option>
                <option value="rerank">rerank</option>
              </select>
            </Row>
          </div>
        </div>
      </div>
    </Section>
  );
}

// ---- Server status + LLM editor --------------------------------------------

function ServerSection({ ctx }: { ctx: ServerCtx }) {
  const { server, llm, err, setServerBoolean } = ctx;
  const { t } = useI18n();

  // Pending-task backlog shown while the worker is stopped (PRD R2 / design
  // 6.2): fetch the running-count once the worker is confirmed off. A single
  // fetch on the off-transition is enough — the count is a hint ("tasks will
  // sit unprocessed"), not a live meter like StatusBar's polling.
  const [pendingCount, setPendingCount] = useState<number>(0);
  useEffect(() => {
    let cancelled = false;
    if (!server || server.worker_running) {
      setPendingCount(0);
      return;
    }
    tasks
      .runningCount()
      .then((c) => {
        if (!cancelled) setPendingCount(c.pending);
      })
      .catch(() => {
        /* keep last value */
      });
    return () => {
      cancelled = true;
    };
  }, [server?.worker_running, server?.worker_enabled]);

  if (err) {
    return (
      <Section
        icon={Server}
        title={t.settings.serverTitle}
        subtitle={t.settings.serverSubtitle}
      >
        <div className="flex items-start gap-2.5 rounded-2xl border border-danger/20 bg-danger/10 p-4 text-xs text-danger">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <span>{t.settings.backendUnreachable(err)}</span>
        </div>
      </Section>
    );
  }

  if (!server || !llm) {
    return (
      <Section
        icon={Server}
        title={t.settings.serverTitle}
        subtitle={t.settings.serverSubtitle}
      >
        <p className="text-xs text-fg-subtle">{t.common.loading}</p>
      </Section>
    );
  }

  return (
    <Section
      icon={Server}
      title={t.settings.serverStatusTitle}
      subtitle={t.settings.serverStatusSubtitle}
    >
        <div className="rounded-2xl border border-border/70 bg-bg-subtle/40 p-5">
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-xs">
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.appEnv}</span>
              <span className="font-bold text-fg-base">{server.app_env}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.home}</span>
              <span className="font-mono text-[11px] text-fg-base truncate max-w-[200px]" title={server.library_home}>{server.library_home}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.db}</span>
              <span className="font-bold text-fg-base">{server.db_backend}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.storage}</span>
              <span className="font-bold text-fg-base">{server.storage_backend}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.worker}</span>
              <span className="flex items-center gap-2">
                <label className="flex cursor-pointer select-none items-center gap-1.5">
                  <input
                    type="checkbox"
                    className="accent-accent h-3.5 w-3.5"
                    checked={Boolean(server.worker_enabled)}
                    onChange={(e) => setServerBoolean("worker_enabled", e.target.checked)}
                  />
                  <span className={cn("font-bold", server.worker_enabled ? "text-accent" : "text-fg-muted")}>
                    {server.worker_enabled ? t.common.enabled : t.common.disabled}
                  </span>
                </label>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                    server.worker_running
                      ? "bg-emerald-500/15 text-emerald-600"
                      : "bg-warning/15 text-warning",
                  )}
                >
                  {server.worker_running ? t.settings.kv.workerRunning : t.settings.kv.workerStopped}
                </span>
              </span>
            </div>
            {server.worker_enabled && !server.worker_running && (
              <div className="col-span-2 -mt-1 pb-2 text-[11px] text-warning">
                {t.settings.workerNotRunningWarning}
              </div>
            )}
            {!server.worker_running && pendingCount > 0 && (
              <div className="col-span-2 -mt-1 pb-2 text-[11px] text-warning">
                {t.settings.workerPendingWarning(pendingCount)}
              </div>
            )}
            <div className="col-span-2 -mt-1 pb-2 text-[11px] text-fg-subtle">
              {t.settings.workerToggleHint}
            </div>
            {server.worker_batch_size != null && (
              <div className="flex items-center justify-between border-b border-border/40 pb-2">
                <span className="text-fg-muted">{t.settings.kv.concurrentIngest}</span>
                <span className="font-mono font-bold text-fg-base">{String(server.worker_batch_size)}</span>
              </div>
            )}
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.autoLifecycle}</span>
              <span className={cn("font-bold", server.auto_lifecycle_enabled ? "text-accent" : "text-fg-muted")}>
                {server.auto_lifecycle_enabled ? t.common.enabled : t.common.disabled}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.conflict}</span>
              <span className="font-mono font-bold text-fg-base">{server.default_on_conflict}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.tokenBudget}</span>
              <span className="font-mono text-[11px] font-bold text-fg-base">
                {`${server.agent_plan_max_tokens.toLocaleString()} / ${server.agent_execute_max_tokens.toLocaleString()}`}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.executeTurns}</span>
              <span className="font-mono font-bold text-fg-base">{String(server.agent_execute_max_turns)}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.compression}</span>
              <span className={cn("font-bold", server.compression_enabled ? "text-accent" : "text-fg-muted")}>
                {server.compression_enabled ? t.common.enabled : t.common.disabled}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.ingestConcurrency}</span>
              <span className="font-mono font-bold text-fg-base">{String(server.llm_ingest_concurrency)}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.semanticRecall}</span>
              <span className="font-semibold text-fg-base">
                {capabilityStatus(server.semantic_recall_enabled, server.embedding_api_key_set, t)}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.embedding}</span>
              <span className="font-mono text-[11px] font-bold text-fg-base truncate max-w-[180px]" title={`${server.embedding_provider}/${server.embedding_model}`}>
                {`${server.embedding_provider}/${server.embedding_model}`}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.rerank}</span>
              <span className="font-semibold text-fg-base">
                {capabilityStatus(server.rerank_enabled, server.rerank_api_key_set, t)}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.evidenceSelection}</span>
              <span className="font-mono font-bold text-fg-base">{server.evidence_selection}</span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.documentVision}</span>
              <span className={cn("font-bold", server.document_vision_enabled ? "text-accent" : "text-fg-muted")}>
                {server.document_vision_enabled ? t.common.enabled : t.common.disabled}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/40 pb-2">
              <span className="text-fg-muted">{t.settings.kv.vision}</span>
              <span className={cn("font-bold", visionConfigured(llm) ? "text-accent" : "text-fg-muted")}>
                {visionConfigured(llm) ? t.settings.visionConfigured : t.settings.visionMissing}
              </span>
            </div>
          </dl>
        </div>
    </Section>
  );
}

function LlmSection({ ctx }: { ctx: ServerCtx }) {
  const { llm, setLlm, err } = ctx;
  const { t } = useI18n();

  if (err) {
    return (
      <Section
        icon={Cpu}
        title={t.settings.llmProfilesTitle}
        subtitle={t.settings.llmProfilesSubtitle}
      >
        <div className="flex items-start gap-2.5 rounded-2xl border border-danger/20 bg-danger/10 p-4 text-xs text-danger">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <span>{t.settings.backendUnreachable(err)}</span>
        </div>
      </Section>
    );
  }

  if (!llm) {
    return (
      <Section
        icon={Cpu}
        title={t.settings.llmProfilesTitle}
        subtitle={t.settings.llmProfilesSubtitle}
      >
        <p className="text-xs text-fg-subtle">{t.common.loading}</p>
      </Section>
    );
  }

  return (
    <Section
      icon={Cpu}
      title={t.settings.llmProfilesTitle}
      subtitle={t.settings.llmProfilesSubtitle}
    >
      <LlmProfileEditor data={llm} onChange={setLlm} />
    </Section>
  );
}

// ---- shared bits -----------------------------------------------------------

function Section({
  icon: Icon,
  title,
  subtitle,
  children,
}: {
  icon?: React.ElementType;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border/80 bg-bg-card p-6 sm:p-7 shadow-xs transition-all">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20 shadow-xs">
            <Icon size={16} />
          </div>
        )}
        <div>
          <h2 className="text-sm font-bold text-fg-base tracking-tight">{title}</h2>
          {subtitle && <p className="text-xs text-fg-subtle">{subtitle}</p>}
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-5">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-bold text-fg-base">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-fg-subtle leading-relaxed">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function Kv({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-fg-muted">{k}</dt>
      <dd className={cn("truncate font-semibold text-fg-base", mono && "font-mono text-xs")}>{v}</dd>
    </>
  );
}

function formatDateTime(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function capabilityStatus(
  enabled: boolean,
  keySet: boolean,
  t: ReturnType<typeof useI18n>["t"],
): string {
  if (!enabled) return t.common.disabled;
  return keySet ? t.common.enabled : t.settings.enabledMissingKey;
}

function semanticIndexStatusLabel(
  server: ServerSettings,
  t: ReturnType<typeof useI18n>["t"],
): string {
  const index = server.semantic_index;
  if (!index?.exists) return t.settings.semanticIndexMissing;
  if (index.needs_rebuild || !index.compatible) return t.settings.semanticIndexNeedsRebuild;
  return t.settings.semanticIndexReady(index.entries);
}

function NumberInput({
  value,
  disabled,
  min,
  max,
  step,
  className,
  onCommit,
}: {
  value: number | undefined;
  disabled?: boolean;
  min: number;
  max: number;
  step: number;
  className?: string;
  onCommit: (v: number) => void;
}) {
  const [draft, setDraft] = useState<string>(value != null ? String(value) : "");
  useEffect(() => {
    setDraft(value != null ? String(value) : "");
  }, [value]);

  const commit = () => {
    const n = parseInt(draft, 10);
    if (!Number.isFinite(n) || n < min || n > max || n === value) {
      setDraft(value != null ? String(value) : "");
      return;
    }
    onCommit(n);
  };

  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={draft}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      className={cn(
        "h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 text-right font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all disabled:opacity-50",
        className,
      )}
    />
  );
}

function TextInput({
  value,
  disabled,
  className,
  onCommit,
}: {
  value: string | undefined;
  disabled?: boolean;
  className?: string;
  onCommit: (v: string) => void;
}) {
  const [draft, setDraft] = useState<string>(value ?? "");
  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  const commit = () => {
    const v = draft.trim();
    if (!v || v === value) {
      setDraft(value ?? "");
      return;
    }
    onCommit(v);
  };

  return (
    <input
      value={draft}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      className={cn(
        "h-10 rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all disabled:opacity-50",
        className,
      )}
    />
  );
}

function SecretInput({
  configured,
  disabled,
  onCommit,
}: {
  configured: boolean;
  disabled?: boolean;
  onCommit: (v: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const commit = async () => {
    const v = draft.trim();
    if (!v || saving) return;
    setSaving(true);
    try {
      await onCommit(v);
      setDraft("");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex items-center gap-2.5">
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-fg-subtle">
          <Key size={14} />
        </div>
        <input
          type="password"
          value={draft}
          disabled={disabled || saving}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void commit();
          }}
          placeholder={configured ? t.settings.secretConfigured : t.common.unset}
          className="h-10 w-56 rounded-xl border border-border/80 bg-bg-base/70 pl-9 pr-3.5 font-mono text-xs focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all disabled:opacity-50"
        />
      </div>
      <button
        type="button"
        title={t.common.save}
        onClick={() => void commit()}
        disabled={disabled || saving || !draft.trim()}
        className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-border/80 bg-bg-card text-fg-muted hover:text-fg-base hover:bg-bg-subtle active:scale-95 disabled:opacity-40 transition-all shadow-xs"
      >
        <Save size={14} />
      </button>
    </div>
  );
}

function visionConfigured(llm: LlmSettings): boolean {
  const v = llm.profiles.vision;
  return Boolean(v?.api_key_set || v?.base_url || v?.model);
}
