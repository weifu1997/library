/** Per-profile LLM editor.
 *
 *  The panel is structured as a quick-config flow for the *default*
 *  profile plus an "advanced" section for per-task overrides:
 *
 *    - A row of provider presets (OpenAI / DashScope / DeepSeek / Kimi)
 *      that auto-fill provider, model, and base URL into the default
 *      form. The default card scrolls into view and the filled fields
 *      flash briefly so the change is visible above the fold; the fill
 *      is staged in the form only until the user presses Save (the row
 *      header marks pending edits as "unsaved").
 *    - The default form, open by default, with an api-key "set / missing"
 *      badge and its own Save (PUT with PATCH semantics — only
 *      `llm_default_*` fields change).
 *    - "Test connection" probes ONLY the default profile
 *      (`POST /v1/settings/llm/test?profile=default`), skipping
 *      embedding/rerank.
 *    - chat / reflect / ingest / vision live under a single "Advanced"
 *      collapsible, closed by default.
 *
 *  The api_key field is special: we never receive the raw value (server
 *  masks it), so the input shows a placeholder telling the user a key
 *  is set. Typing replaces it; leaving it blank keeps whatever's
 *  already configured. */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Save,
  RotateCcw,
  Loader2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ChevronDown,
  Sparkles,
  MessageSquare,
  Compass,
  Layers,
  Eye,
  Settings2,
  Check,
  Key,
  Zap,
  LifeBuoy,
} from "lucide-react";

import { settings as settingsApi } from "@/api/client";
import type { LlmTestResult } from "@/api/client";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { LlmModelInfo, LlmProfileName, LlmSettings } from "@/types/api";

const ADVANCED_PROFILES: LlmProfileName[] = ["chat", "reflect", "ingest", "vision"];
const EDITABLE_FIELDS = [
  "provider", "model", "base_url", "api_key", "dialect", "context_window",
  "tokenizer", "supports_vision", "supports_tools", "supports_temperature",
  "token_limit_param",
] as const;
const BACKUP_FIELDS = [
  "backup_provider", "backup_model", "backup_base_url", "backup_api_key",
] as const;
const FORM_FIELDS = [...EDITABLE_FIELDS, ...BACKUP_FIELDS] as const;

type FormState = Partial<Record<string, string>>;

/** Server masks stored api_keys in GET responses ("sk-***CA"), so the form
 *  never holds a raw credential — a masked placeholder must never be sent
 *  back as a live value (fetching would 401, saving would overwrite the
 *  real stored key). Empty / unmasked values still pass through. */
const isMaskedKey = (v: string | undefined | null): boolean =>
  !!v && v.includes("***");

/** A one-click provider shortcut that fills the default profile's
 *  provider / model / base_url. Every field stays editable afterwards. */
interface ProviderPreset {
  key: string;
  label: string;
  provider: string;
  base_url: string;
  model: string;
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    key: "openai", label: "OpenAI", provider: "openai",
    base_url: "https://api.openai.com/v1", model: "gpt-4o-mini",
  },
  {
    key: "dashscope", label: "通义千问", provider: "openai-compatible",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    key: "deepseek", label: "DeepSeek", provider: "openai-compatible",
    base_url: "https://api.deepseek.com/v1", model: "deepseek-chat",
  },
  {
    key: "moonshot", label: "Kimi", provider: "openai-compatible",
    base_url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k",
  },
];

interface Props {
  data: LlmSettings;
  onChange: (next: LlmSettings) => void;
}

export function LlmProfileEditor({ data, onChange }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState<LlmProfileName | null>("default");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [preset, setPreset] = useState<ProviderPreset | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<LlmTestResult | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);

  const applyPreset = (p: ProviderPreset) => {
    // Spread so clicking the same preset twice still re-fires the effect.
    setPreset({ ...p });
    setOpen("default");
    // Bring the default quick-config form into view so the fill is
    // visible even when presets sit above the fold on short screens.
    window.setTimeout(() => {
      document.getElementById("llm-default-row")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }, 0);
  };

  const runTest = async () => {
    setTesting(true);
    setTestErr(null);
    setTestResult(null);
    try {
      const res = await settingsApi.testLlmDefault();
      setTestResult(res.profiles.default);
    } catch (e: unknown) {
      setTestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-fg-subtle">
          {t.settings.llmProfilesSubtitle}
        </p>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline text-[11px] text-fg-subtle">
            {t.llm.testDefaultHint}
          </span>
          <button
            onClick={runTest}
            disabled={testing}
            className={cn(
              "inline-flex h-10 items-center gap-2 rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-base shadow-xs",
              "hover:bg-bg-subtle hover:border-border active:scale-[0.98] transition-all disabled:opacity-50",
            )}
          >
            {testing ? <Loader2 size={14} className="animate-spin text-accent" /> : <Sparkles size={14} className="text-accent" />}
            {testing ? t.llm.testing : t.llm.testConnection}
          </button>
        </div>
      </div>

      {testErr && (
        <div className="flex items-start gap-2.5 rounded-2xl border border-danger/20 bg-danger/10 p-3.5 text-xs text-danger">
          <XCircle size={15} className="mt-0.5 shrink-0" />
          <span>{testErr}</span>
        </div>
      )}

      {testResult && (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-border/80 bg-bg-subtle/50 p-3.5 text-xs">
          <span className="text-[11px] font-bold uppercase tracking-wider text-fg-muted">
            {t.llm.testConnection}
          </span>
          <TestStatus result={testResult} />
        </div>
      )}

      {/* Provider presets → default profile */}
      <div className="rounded-2xl border border-border/80 bg-bg-card p-5 shadow-xs">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-accent" />
          <span className="text-xs font-bold text-fg-base">{t.llm.presets}</span>
        </div>
        <p className="mt-1 text-[11px] text-fg-subtle">{t.llm.presetsHint}</p>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {PROVIDER_PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => applyPreset(p)}
              className={cn(
                "group flex flex-col items-start rounded-xl border border-border/70 bg-bg-base/60 px-3 py-2.5 text-left",
                "hover:border-accent/50 hover:bg-bg-subtle active:scale-[0.98] transition-all",
                preset?.key === p.key && "border-accent/60 bg-accent/5 ring-1 ring-accent/20",
              )}
            >
              <span className="text-xs font-bold text-fg-base">{p.label}</span>
              <span className="mt-0.5 w-full truncate font-mono text-[10px] text-fg-subtle" title={p.model}>
                {p.model}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Default profile (quick config) */}
      <div id="llm-default-row">
        <ProfileRow
          name="default"
          data={data}
          preset={preset}
          isOpen={open === "default"}
          onToggle={() => setOpen(open === "default" ? null : "default")}
          onChange={onChange}
        />
      </div>

      {/* Advanced profiles — collapsed by default */}
      <div className="overflow-hidden rounded-2xl border border-border/80 bg-bg-card shadow-xs">
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className={cn(
            "flex min-h-[52px] w-full items-center justify-between gap-3 px-5 py-3.5 text-left transition-colors",
            advancedOpen ? "bg-bg-subtle/50" : "hover:bg-bg-subtle/30",
          )}
        >
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-sm transition-colors",
                advancedOpen
                  ? "border-accent/30 bg-accent/10 text-accent"
                  : "border-border/60 bg-bg-subtle text-fg-muted",
              )}
            >
              <Settings2 size={18} />
            </div>
            <div className="min-w-0">
              <span className="text-sm font-bold text-fg-base">
                {t.llm.advancedProfiles}
              </span>
              <p className="mt-0.5 text-xs text-fg-subtle">
                {t.llm.advancedProfilesHint}
              </p>
            </div>
          </div>
          <ChevronDown
            size={18}
            className={cn(
              "shrink-0 text-fg-muted transition-transform duration-200",
              advancedOpen && "rotate-180 text-fg-base",
            )}
          />
        </button>

        {advancedOpen && (
          <div className="space-y-3 border-t border-border/70 bg-bg-base/30 p-4">
            {ADVANCED_PROFILES.map((name) => (
              <ProfileRow
                key={name}
                name={name}
                data={data}
                isOpen={open === name}
                onToggle={() => setOpen(open === name ? null : name)}
                onChange={onChange}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TestStatus({ result }: { result: LlmTestResult }) {
  const { t } = useI18n();
  if (result.ok === null) {
    return <span className="text-[11px] text-fg-subtle">{t.llm.testNotConfigured}</span>;
  }
  if (result.ok) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
        <CheckCircle2 size={14} className="shrink-0" />
        {t.llm.testOk}
        {result.model && (
          <span className="truncate max-w-[120px] font-mono text-[11px] text-fg-subtle" title={result.model}>
            · {result.model}
          </span>
        )}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-danger">
      <XCircle size={14} className="shrink-0" />
      <span className="truncate max-w-[140px]" title={result.error || undefined}>
        {result.error || "error"}
      </span>
    </span>
  );
}

interface RowProps {
  name: LlmProfileName;
  data: LlmSettings;
  preset?: ProviderPreset | null;
  isOpen: boolean;
  onToggle: () => void;
  onChange: (next: LlmSettings) => void;
}

function getProfileIcon(name: LlmProfileName) {
  switch (name) {
    case "default":
      return Settings2;
    case "chat":
      return MessageSquare;
    case "reflect":
      return Compass;
    case "ingest":
      return Layers;
    case "vision":
      return Eye;
  }
}

function ProfileRow({ name, data, preset, isOpen, onToggle, onChange }: RowProps) {
  const { t } = useI18n();
  const isDefault = name === "default";
  const profile = isDefault ? null : data.profiles[name];
  const overlay = data.overlay;
  // Must be stable across renders: `initialForm`'s useMemo and the form-sync
  // effect depend on it, and a fresh function every render would re-run the
  // effect and wipe user edits on every keystroke.
  const overlayKey = useCallback(
    (suffix: string) =>
      isDefault ? `llm_default_${suffix}` : `llm_${name}_${suffix}`,
    [isDefault, name],
  );

  const view = isDefault ? data.defaults : (profile ?? data.defaults);

  // Backup (failover) target: `view.backup` is null when nothing is
  // configured (the vision profile's raw payload stays null even when a
  // default backup exists). Placeholders reflect the resolved value.
  const backupView = view.backup ?? null;
  const defaultBackup = data.defaults.backup;
  const backupInheritLabel = defaultBackup
    ? `(Inherit: ${defaultBackup.provider || "openai-compatible"})`
    : t.llm.backupNotConfigured;
  const backupPlaceholder = (val: string | null | undefined) =>
    val ?? t.llm.backupNotConfigured;

  const initialForm = useMemo<FormState>(() => {
    const f: FormState = {};
    for (const key of FORM_FIELDS) {
      const v = overlay[overlayKey(key)];
      if (v !== undefined && v !== null) {
        f[key] = String(v);
      }
    }
    return f;
  }, [overlay, overlayKey]);

  const [form, setForm] = useState<FormState>(initialForm);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [healed, setHealed] = useState<number>(0);

  // Model-listing state for the primary and backup model fields. Two
  // independent copies so fetching for one never repopulates the other.
  const [models, setModels] = useState<LlmModelInfo[] | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchErr, setFetchErr] = useState<string | null>(null);
  const [backupModels, setBackupModels] = useState<LlmModelInfo[] | null>(null);
  const [fetchingBackup, setFetchingBackup] = useState(false);
  const [fetchErrBackup, setFetchErrBackup] = useState<string | null>(null);

  useEffect(() => {
    setForm(initialForm);
    setDirty(false);
  }, [initialForm]);

  // A provider preset fills provider / model / base_url into the default
  // form and marks it dirty so Save is enabled. Only the default row uses
  // this; the spread in applyPreset gives presets fresh identity so
  // clicking the same one twice still applies. The affected controls get
  // a brief ring flash so the fill reads as an explicit change.
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!isDefault || !preset) return;
    setForm((prev) => ({
      ...prev,
      provider: preset.provider,
      base_url: preset.base_url,
      model: preset.model,
    }));
    setDirty(true);
    setFlash(true);
  }, [isDefault, preset]);
  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(false), 1800);
    return () => window.clearTimeout(t);
  }, [flash]);

  const updateField = (field: string, val: string) => {
    setForm((prev) => ({ ...prev, [field]: val }));
    setDirty(true);
  };

  // Fetch the provider's model list for a field. Sends the current form
  // values (provider/base_url/api_key) so an unsaved edit can be listed;
  // empty fields fall back to the saved resolution server-side.
  const fetchModels = async (kind: "model" | "backup_model") => {
    const isBackup = kind === "backup_model";
    const p = isBackup ? "backup_" : "";
    const setF = isBackup ? setFetchingBackup : setFetching;
    const setE = isBackup ? setFetchErrBackup : setFetchErr;
    const setM = isBackup ? setBackupModels : setModels;
    setF(true);
    setE(null);
    setM(null);
    try {
      const rawKey = form[`${p}api_key`];
      const res = await settingsApi.fetchLlmModels({
        profile: name,
        backup: isBackup,
        provider: form[`${p}provider`] || null,
        base_url: form[`${p}base_url`] || null,
        // A masked placeholder is the saved key, not a live override —
        // send null so the server resolves the real stored key.
        api_key: isMaskedKey(rawKey) ? null : (rawKey?.trim() || null),
      });
      if (!res.ok) {
        setE(res.error ?? "fetch failed");
        return;
      }
      setM(res.models ?? []);
    } catch (e: unknown) {
      setE(e instanceof Error ? e.message : String(e));
    } finally {
      setF(false);
    }
  };

  const overrideCount = useMemo(
    () => FORM_FIELDS.filter((k) => overlay[overlayKey(k)] !== undefined).length,
    [overlay, overlayKey],
  );

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const patch: Record<string, string | number | boolean | null> = {};
      const fields = [
        "provider", "model", "base_url", "api_key", "dialect",
        "tokenizer", "token_limit_param",
        "backup_provider", "backup_model", "backup_base_url", "backup_api_key",
      ];
      for (const f of fields) {
        if (f in form) {
          const val = form[f]?.trim();
          // Masked placeholder = the already-stored key; skip it so the
          // real key in the overlay is preserved (a blank field still
          // clears, as before).
          if ((f === "api_key" || f === "backup_api_key") && isMaskedKey(val)) {
            continue;
          }
          patch[overlayKey(f)] = val === "" ? null : (val ?? null);
        }
      }
      if ("context_window" in form) {
        const val = form.context_window?.trim();
        patch[overlayKey("context_window")] = val === "" ? null : parseInt(val || "0", 10);
      }
      const boolFields = ["supports_vision", "supports_tools", "supports_temperature"];
      for (const f of boolFields) {
        if (f in form) {
          const val = form[f]?.trim();
          patch[overlayKey(f)] = val === "" ? null : val === "true";
        }
      }

      const res = await settingsApi.updateLlm(patch);
      onChange(res);
      setSavedAt(Date.now());
      setHealed(res.reprocessed_failed ?? 0);
      setDirty(false);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    setErr(null);
    try {
      const patch: Record<string, null> = {};
      for (const f of FORM_FIELDS) {
        patch[overlayKey(f)] = null;
      }
      const res = await settingsApi.updateLlm(patch);
      onChange(res);
      setSavedAt(Date.now());
      setDirty(false);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const Icon = getProfileIcon(name);
  const isConfigured = view.api_key_set || !isDefault;

  // While the form holds unsaved edits the header preview shows those
  // pending values (with an "unsaved" tag) instead of the stored ones —
  // preset fills and manual edits are visible without scrolling to Save.
  const flashClass = "border-accent ring-2 ring-accent/40";
  const shownProvider =
    dirty && form.provider !== undefined && form.provider !== ""
      ? form.provider
      : view.provider;
  const shownModel =
    dirty && form.model ? form.model : view.model;

  return (
    <div className="overflow-hidden rounded-2xl border border-border/80 bg-bg-card shadow-xs transition-all">
      {/* Header button — 56px height standard */}
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "flex min-h-[56px] w-full items-center justify-between gap-3 px-5 py-3.5 text-left transition-colors",
          isOpen ? "bg-bg-subtle/50" : "hover:bg-bg-subtle/30",
        )}
      >
        <div className="flex min-w-0 items-center gap-3.5">
          <div
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-sm transition-colors",
              isOpen
                ? "border-accent/30 bg-accent/10 text-accent"
                : "border-border/60 bg-bg-subtle text-fg-muted",
            )}
          >
            <Icon size={18} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold capitalize text-fg-base">
                {name}
              </span>
              {isDefault ? (
                <span className="rounded-md border border-accent/20 bg-accent/10 px-2 py-0.5 text-[11px] font-semibold text-accent">
                  Default Base
                </span>
              ) : (
                <span
                  className={cn(
                    "rounded-md border px-2 py-0.5 text-[11px] font-semibold",
                    overrideCount > 0
                      ? "border-accent/20 bg-accent/10 text-accent"
                      : "border-border/60 bg-bg-subtle text-fg-muted",
                  )}
                >
                  {overrideCount > 0 ? t.llm.override(overrideCount) : t.llm.inherited}
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate font-mono text-xs text-fg-subtle">
              {shownProvider || "openai-compatible"} · {shownModel || "(unset)"}
              {dirty && (
                <span className="ml-1.5 inline-flex items-center rounded-md border border-warning/30 bg-warning/10 px-1.5 py-0.5 font-sans text-[10px] font-semibold text-warning">
                  {t.llm.unsaved}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2.5">
          <div
            className={cn(
              "h-2.5 w-2.5 rounded-full",
              isConfigured ? "bg-accent shadow-xs" : "bg-warning",
            )}
          />
          <ChevronDown
            size={18}
            className={cn(
              "text-fg-muted transition-transform duration-200",
              isOpen && "rotate-180 text-fg-base",
            )}
          />
        </div>
      </button>

      {/* Expanded body */}
      {isOpen && (
        <div className="space-y-4.5 border-t border-border/70 bg-bg-card p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t.llm.provider}>
              <select
                value={form.provider ?? ""}
                onChange={(e) => updateField("provider", e.target.value)}
                className={cn(
                  "h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs font-medium outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20",
                  flash && flashClass,
                )}
              >
                <option value="">
                  {isDefault ? "openai-compatible" : `(Inherit: ${data.defaults.provider || "openai-compatible"})`}
                </option>
                <option value="openai">OpenAI</option>
                <option value="openai-compatible">OpenAI Compatible (Ollama, LM Studio, vLLM, DeepSeek)</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </Field>

            <div>
              <Field label={t.llm.model}>
                <ModelListPicker
                  fetching={fetching}
                  error={fetchErr}
                  models={models}
                  value={form.model ?? ""}
                  flash={flash}
                  onPick={(v) => updateField("model", v)}
                  onManual={() => setModels([])}
                  onFetch={() => fetchModels("model")}
                  labels={{ fetch: t.llm.fetchModels, fetching: t.llm.fetchingModels, pick: t.llm.pickModel, manual: t.llm.typeModel }}
                  placeholder={isDefault ? "e.g. gpt-4o-mini, deepseek-chat, qwen-plus" : (view.model || undefined)}
                />
              </Field>
            </div>

            <div className="sm:col-span-2">
              <Field label={t.llm.baseUrl}>
                <input
                  value={form.base_url ?? ""}
                  onChange={(e) => updateField("base_url", e.target.value)}
                  placeholder={isDefault ? "https://api.openai.com/v1" : (view.base_url || "https://api.openai.com/v1")}
                  className={cn(
                    "h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20",
                    flash && flashClass,
                  )}
                />
              </Field>
            </div>

            <div className="sm:col-span-2">
              <Field label={t.llm.apiKey}>
                <div className="mb-1.5 flex items-center gap-2">
                  {view.api_key_set ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-success-subtle px-2 py-0.5 text-[11px] font-semibold text-success">
                      <Check size={11} />
                      {t.llm.keyConfigured}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-bg-muted px-2 py-0.5 text-[11px] font-semibold text-fg-muted">
                      <XCircle size={11} />
                      {t.llm.keyMissing}
                    </span>
                  )}
                </div>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-fg-subtle">
                    <Key size={14} />
                  </div>
                  <input
                    type="password"
                    value={form.api_key ?? ""}
                    onChange={(e) => updateField("api_key", e.target.value)}
                    placeholder={
                      view.api_key_set
                        ? t.common.setValue(view.api_key ?? "")
                        : t.common.unset
                    }
                    className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 pl-9 pr-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
                  />
                </div>
                <p className="mt-1 text-[11px] text-fg-subtle">
                  {t.llm.keepKeyHint}
                </p>
              </Field>
            </div>

            <Field label={t.llm.dialect}>
              <select
                value={form.dialect ?? ""}
                onChange={(e) => updateField("dialect", e.target.value)}
                className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
              >
                <option value="">{isDefault ? "standard" : `(Inherit: ${view.capabilities?.dialect || "standard"})`}</option>
                <option value="standard">standard</option>
                <option value="openrouter">openrouter</option>
                <option value="azure">azure</option>
                <option value="ollama">ollama</option>
              </select>
            </Field>

            <Field label={t.llm.contextWindow}>
              <input
                type="number"
                min={1024}
                value={form.context_window ?? ""}
                onChange={(e) => updateField("context_window", e.target.value)}
                placeholder={String(view.capabilities?.context_window || 128000)}
                className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </Field>

            <Field label={t.llm.tokenizer}>
              <input
                value={form.tokenizer ?? ""}
                onChange={(e) => updateField("tokenizer", e.target.value)}
                placeholder={view.capabilities?.tokenizer || "cl100k_base"}
                className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </Field>

            <Field label={t.llm.tokenLimitParam}>
              <select
                value={form.token_limit_param ?? ""}
                onChange={(e) => updateField("token_limit_param", e.target.value)}
                className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
              >
                <option value="">{view.capabilities?.token_limit_param || "max_tokens"}</option>
                <option value="max_tokens">max_tokens</option>
                <option value="max_completion_tokens">max_completion_tokens</option>
              </select>
            </Field>

            <CapabilitySelect
              label={t.llm.supportsVision}
              value={form.supports_vision ?? ""}
              inherited={Boolean(view.capabilities?.supports_vision)}
              onChange={(value) => updateField("supports_vision", value)}
            />
            <CapabilitySelect
              label={t.llm.supportsTools}
              value={form.supports_tools ?? ""}
              inherited={Boolean(view.capabilities?.supports_tools)}
              onChange={(value) => updateField("supports_tools", value)}
            />
            <CapabilitySelect
              label={t.llm.supportsTemperature}
              value={form.supports_temperature ?? ""}
              inherited={Boolean(view.capabilities?.supports_temperature)}
              onChange={(value) => updateField("supports_temperature", value)}
            />
          </div>

          {/* Backup (failover) model — a second endpoint used when the
              primary exhausts its transient-retry budget. */}
          <div className="rounded-2xl border border-border/70 bg-bg-base/40 p-4">
            <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <LifeBuoy size={14} className="shrink-0 text-fg-muted" />
              <span className="text-xs font-bold text-fg-base">{t.llm.backupSection}</span>
              <span className="text-[11px] text-fg-subtle">{t.llm.backupHint}</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t.llm.provider}>
                <select
                  value={form.backup_provider ?? ""}
                  onChange={(e) => updateField("backup_provider", e.target.value)}
                  className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
                >
                  <option value="">
                    {isDefault ? t.llm.backupNotConfigured : backupInheritLabel}
                  </option>
                  <option value="openai">OpenAI</option>
                  <option value="openai-compatible">OpenAI Compatible (Ollama, LM Studio, vLLM, DeepSeek)</option>
                  <option value="anthropic">Anthropic Claude</option>
                </select>
              </Field>

              <div>
                <Field label={t.llm.model}>
                  <ModelListPicker
                    fetching={fetchingBackup}
                    error={fetchErrBackup}
                    models={backupModels}
                    value={form.backup_model ?? ""}
                    onPick={(v) => updateField("backup_model", v)}
                    onManual={() => setBackupModels([])}
                    onFetch={() => fetchModels("backup_model")}
                    labels={{ fetch: t.llm.fetchModels, fetching: t.llm.fetchingModels, pick: t.llm.pickModel, manual: t.llm.typeModel }}
                    placeholder={backupPlaceholder(backupView?.model)}
                  />
                </Field>
              </div>

              <div className="sm:col-span-2">
                <Field label={t.llm.baseUrl}>
                  <input
                    value={form.backup_base_url ?? ""}
                    onChange={(e) => updateField("backup_base_url", e.target.value)}
                    placeholder={backupPlaceholder(backupView?.base_url)}
                    className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
                  />
                </Field>
              </div>

              <div className="sm:col-span-2">
                <Field label={t.llm.apiKey}>
                  <div className="mb-1.5 flex items-center gap-2">
                    {backupView?.api_key_set ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-success-subtle px-2 py-0.5 text-[11px] font-semibold text-success">
                        <Check size={11} />
                        {t.llm.keyConfigured}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-bg-muted px-2 py-0.5 text-[11px] font-semibold text-fg-muted">
                        <XCircle size={11} />
                        {t.llm.keyMissing}
                      </span>
                    )}
                  </div>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-fg-subtle">
                      <Key size={14} />
                    </div>
                    <input
                      type="password"
                      value={form.backup_api_key ?? ""}
                      onChange={(e) => updateField("backup_api_key", e.target.value)}
                      placeholder={
                        backupView?.api_key_set
                          ? t.common.setValue(backupView.api_key ?? "")
                          : t.common.unset
                      }
                      className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 pl-9 pr-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-fg-subtle">{t.llm.keepKeyHint}</p>
                </Field>
              </div>
            </div>
          </div>

          {err && (
            <div className="flex items-start gap-2 rounded-xl border border-danger/20 bg-danger/10 px-3.5 py-2.5 text-xs text-danger">
              <XCircle size={15} className="mt-0.5 shrink-0" />
              <span>{err}</span>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
            <button
              onClick={reset}
              disabled={saving || (isDefault ? false : overrideCount === 0)}
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-border/80 px-4 text-xs font-semibold text-fg-muted shadow-xs transition-all hover:bg-bg-subtle hover:text-fg-base active:scale-95 disabled:opacity-40"
            >
              <RotateCcw size={13} /> {t.llm.reset}
            </button>

            <div className="flex items-center gap-3.5">
              {savedAt && !saving && (
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent">
                  <Check size={14} />
                  {t.common.saved}
                </span>
              )}
              {healed > 0 && !saving && (
                <span className="text-xs font-medium text-accent">
                  {t.llm.reprocessedFailed(healed)}
                </span>
              )}
              <button
                onClick={save}
                disabled={!dirty || saving}
                className={cn(
                  "inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-xs font-semibold text-accent-fg shadow-xs",
                  "transition-all hover:bg-accent-hover active:scale-[0.98] disabled:opacity-40 shadow-indigo-500/20",
                )}
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                {t.common.save}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-xs font-semibold text-fg-base">{label}</span>
      {children}
    </label>
  );
}

function CapabilitySelect({
  label,
  value,
  inherited,
  onChange,
}: {
  label: string;
  value: string;
  inherited: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20"
      >
        <option value="">(Inherit: {String(inherited)})</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    </Field>
  );
}

/** Single model control for a model field — a text input until a fetch
 *  succeeds, then the input is *replaced* by a dropdown (never two controls).
 *  The fetch button + error sit below. Picking writes back via `onPick`; the
 *  "type manually" escape falls back to the input via `onManual`. */
function ModelListPicker({
  fetching,
  error,
  models,
  value,
  flash = false,
  onPick,
  onManual,
  onFetch,
  labels,
  placeholder,
}: {
  fetching: boolean;
  error: string | null;
  models: LlmModelInfo[] | null;
  value: string;
  /** Brief accent ring while a preset fill is being highlighted. */
  flash?: boolean;
  onPick: (v: string) => void;
  onManual: () => void;
  onFetch: () => void;
  labels: { fetch: string; fetching: string; pick: string; manual: string };
  placeholder?: string;
}) {
  const list = models ?? [];
  const hasModels = list.length > 0;
  const controlClass = cn(
    "h-10 w-full rounded-xl border border-border/80 bg-bg-base/70 px-3 font-mono text-xs outline-none transition-all focus:border-accent focus:ring-2 focus:ring-accent/20",
    flash && "border-accent ring-2 ring-accent/40",
  );
  return (
    <div className="space-y-1.5">
      {hasModels ? (
        <select
          value={value}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "__manual__") {
              onManual();
            } else {
              onPick(v);
            }
          }}
          className={controlClass}
        >
          <option value="">{labels.pick}…</option>
          {value && !list.some((m) => m.id === value) && (
            <option value={value}>{value}</option>
          )}
          {list.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name ?? m.id}
            </option>
          ))}
          <option value="__manual__">{labels.manual}</option>
        </select>
      ) : (
        <input
          value={value}
          onChange={(e) => onPick(e.target.value)}
          placeholder={placeholder}
          className={controlClass}
        />
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onFetch}
          disabled={fetching}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-bg-base/70 px-2.5 py-1.5 text-[11px] font-medium text-fg-muted transition-colors hover:bg-bg-base hover:text-fg-base disabled:cursor-not-allowed disabled:opacity-50"
        >
          {fetching ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <RefreshCw size={12} />
          )}
          {fetching ? labels.fetching : labels.fetch}
        </button>
        {error && (
          <span className="min-w-0 flex-1 truncate text-[11px] text-red-500">
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
