/** Per-profile LLM editor.
 *
 *  Each row is one of chat/reflect/ingest/vision. The form starts
 *  prefilled with whatever is in the overlay (so unset fields stay
 *  blank — the placeholder shows the inherited default). Save sends a
 *  PATCH with only the changed fields; clearing a field to empty sends
 *  `null` so the override is removed and the profile falls back to the
 *  default.
 *
 *  The api_key field is special: we never receive the raw value (server
 *  masks it), so the input shows a placeholder telling the user a key
 *  is set. Typing replaces it; leaving it blank keeps whatever's
 *  already configured. */
import { useEffect, useMemo, useState } from "react";
import { Save, RotateCcw, Loader2, CheckCircle2, XCircle } from "lucide-react";

import { settings as settingsApi } from "@/api/client";
import type { LlmTestResult } from "@/api/client";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { LlmProfileName, LlmSettings } from "@/types/api";

const PROFILES: LlmProfileName[] = ["default", "chat", "reflect", "ingest", "vision"];
const EDITABLE_FIELDS = [
  "provider", "model", "base_url", "api_key", "dialect", "context_window",
  "tokenizer", "supports_vision", "supports_tools", "supports_temperature",
  "token_limit_param",
] as const;

type FormState = Partial<Record<string, string>>;

interface Props {
  data: LlmSettings;
  onChange: (next: LlmSettings) => void;
}

export function LlmProfileEditor({ data, onChange }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState<LlmProfileName | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, LlmTestResult> | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);

  const runTest = async () => {
    setTesting(true);
    setTestErr(null);
    try {
      const res = await settingsApi.testLlm();
      setTestResults({
        ...res.profiles,
        embedding: res.embedding,
        rerank: res.rerank,
      });
    } catch (e: unknown) {
      setTestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end">
        <button
          onClick={runTest}
          disabled={testing}
          className={cn(
            "flex items-center gap-1.5 rounded border border-border px-2.5 py-1 text-xs font-medium",
            "hover:bg-bg-subtle disabled:opacity-40",
          )}
        >
          {testing && <Loader2 size={12} className="animate-spin" />}
          {testing ? t.llm.testing : t.llm.testConnection}
        </button>
      </div>

      {testErr && (
        <p className="rounded bg-danger/10 px-2 py-1 text-xs text-danger">{testErr}</p>
      )}

      {testResults && (
        <div className="space-y-1 rounded-md border border-border bg-bg-subtle px-3 py-2 text-xs">
          {Object.entries(testResults).map(([name, r]) => (
            <div key={name} className="flex items-start gap-2">
              <span className="w-16 shrink-0 font-medium capitalize">{name}</span>
              <TestStatus result={r} />
            </div>
          ))}
        </div>
      )}

      {PROFILES.map((name) => (
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
  );
}

function TestStatus({ result }: { result: LlmTestResult }) {
  const { t } = useI18n();
  if (result.ok === null) {
    return <span className="text-fg-subtle">{t.llm.testNotConfigured}</span>;
  }
  if (result.ok) {
    return (
      <span className="flex items-center gap-1 text-accent">
        <CheckCircle2 size={12} className="shrink-0" />
        {t.llm.testOk}
        {result.model && (
          <span className="font-mono text-fg-subtle">· {result.model}</span>
        )}
      </span>
    );
  }
  return (
    <span className="flex items-start gap-1 text-danger">
      <XCircle size={12} className="mt-0.5 shrink-0" />
      <span className="break-all">{result.error}</span>
    </span>
  );
}

interface RowProps {
  name: LlmProfileName;
  data: LlmSettings;
  isOpen: boolean;
  onToggle: () => void;
  onChange: (next: LlmSettings) => void;
}

function ProfileRow({ name, data, isOpen, onToggle, onChange }: RowProps) {
  const { t } = useI18n();
  const isDefault = name === "default";
  const profile = isDefault ? null : data.profiles[name];
  const overlay = data.overlay;
  const optional = name === "vision";
  const overlayKey = (suffix: string) =>
    isDefault ? `llm_default_${suffix}` : `llm_${name}_${suffix}`;

  // Default row reads its "current" view from data.defaults; per-profile
  // rows read from data.profiles[name]. The fields share the same shape
  // (provider/model/base_url/api_key{_set}) so downstream rendering can
  // ignore the difference.
  const view = isDefault
    ? {
        provider: data.defaults.provider,
        model: data.defaults.model,
        base_url: data.defaults.base_url,
        api_key: data.defaults.api_key,
        api_key_set: data.defaults.api_key_set,
        capabilities: data.defaults.capabilities,
      }
    : profile!;

  const [form, setForm] = useState<FormState>({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [healed, setHealed] = useState(0);

  useEffect(() => {
    const overlayValue = (suffix: string) => {
      const value = overlay[overlayKey(suffix)];
      return value == null ? "" : String(value);
    };
    setForm({
      provider: overlayValue("provider"),
      model: overlayValue("model"),
      base_url: overlayValue("base_url"),
      api_key: "",
      dialect: overlayValue("dialect"),
      context_window: overlayValue("context_window"),
      tokenizer: overlayValue("tokenizer"),
      supports_vision: overlayValue("supports_vision"),
      supports_tools: overlayValue("supports_tools"),
      supports_temperature: overlayValue("supports_temperature"),
      token_limit_param: overlayValue("token_limit_param"),
    });
    setErr(null);
    setHealed(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, isOpen]);

  const dirty = useMemo(() => {
    return (
      (form.provider ?? "") !== (overlay[overlayKey("provider")] ?? "") ||
      (form.model ?? "") !== (overlay[overlayKey("model")] ?? "") ||
      (form.base_url ?? "") !== (overlay[overlayKey("base_url")] ?? "") ||
      (form.api_key ?? "") !== "" ||
      EDITABLE_FIELDS.filter((field) => field !== "api_key").some(
        (field) => (form[field] ?? "") !== (
          overlay[overlayKey(field)] == null
            ? ""
            : String(overlay[overlayKey(field)])
        ),
      )
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, overlay, name]);

  const overrideCount = EDITABLE_FIELDS.filter(
    (k) => overlay[overlayKey(k)] != null,
  ).length;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const patch: Record<string, string | null> = {};
      for (const k of EDITABLE_FIELDS) {
        const v = form[k];
        if (v === undefined) continue;
        if (k === "api_key" && v === "") continue;
        if (v === "") patch[overlayKey(k)] = null;
        else patch[overlayKey(k)] = v;
      }
      if (Object.keys(patch).length === 0) {
        setSaving(false);
        return;
      }
      const next = await settingsApi.updateLlm(patch);
      onChange(next);
      setSavedAt(Date.now());
      setHealed(next.reprocessed_failed ?? 0);
      setForm((f) => ({ ...f, api_key: "" }));
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
      for (const k of EDITABLE_FIELDS) {
        patch[overlayKey(k)] = null;
      }
      const next = await settingsApi.updateLlm(patch);
      onChange(next);
      setForm(Object.fromEntries(EDITABLE_FIELDS.map((field) => [field, ""])));
      setSavedAt(Date.now());
      setHealed(0);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-md border border-border bg-bg-base">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-bg-subtle"
      >
        <div className="flex items-center gap-3">
          <span className="font-medium capitalize">{name}</span>
          <span className="font-mono text-xs text-fg-subtle">
            {view.provider || view.model
              ? `${view.provider ?? t.common.unset}/${view.model || t.common.unset}`
              : t.common.unset}
          </span>
        </div>
        <span className="text-xs text-fg-subtle">
          {overrideCount > 0
            ? t.llm.override(overrideCount)
            : optional
              ? view.model || view.api_key_set
                ? t.llm.fromEnv
                : t.common.notConfigured
              : isDefault
                ? view.api_key_set
                  ? t.llm.fromEnv
                  : t.common.notConfigured
                : t.llm.inherited}
        </span>
      </button>

      {isOpen && (
        <div className="space-y-3 border-t border-border px-3 py-3 text-sm">
          <Field label={t.llm.provider}>
            <select
              value={form.provider ?? ""}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
              className="w-full rounded border border-border bg-bg-base px-2 py-1 text-sm"
            >
              <option value="">
                {isDefault
                  ? view.provider
                    ? t.common.fromEnv(view.provider)
                    : t.common.unset
                  : optional
                    ? view.provider
                      ? t.common.fromEnv(view.provider)
                      : t.common.unset
                    : t.common.inherit(data.defaults.provider)}
              </option>
              <option value="openai">openai</option>
              <option value="openai-compatible">openai-compatible</option>
              <option value="anthropic">anthropic</option>
            </select>
          </Field>
          <Field label={t.llm.model}>
            <input
              value={form.model ?? ""}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder={
                isDefault
                  ? view.model
                    ? t.common.fromEnv(view.model)
                    : t.common.unset
                  : optional
                    ? view.model
                      ? t.common.fromEnv(view.model)
                      : t.common.unset
                    : t.common.inherit(data.defaults.model)
              }
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </Field>
          <Field label={t.llm.baseUrl}>
            <input
              value={form.base_url ?? ""}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder={
                isDefault
                  ? view.base_url
                    ? t.common.fromEnv(view.base_url)
                    : t.common.providerDefault
                  : optional
                    ? view.base_url
                      ? t.common.fromEnv(view.base_url)
                      : t.common.unset
                    : data.defaults.base_url || t.common.providerDefault
              }
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </Field>
          <Field label={t.llm.dialect}>
            <input
              value={form.dialect ?? ""}
              onChange={(e) => setForm({ ...form, dialect: e.target.value })}
              placeholder={view.capabilities.dialect}
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </Field>
          <Field label={t.llm.contextWindow}>
            <input
              type="number"
              min={1024}
              value={form.context_window ?? ""}
              onChange={(e) => setForm({ ...form, context_window: e.target.value })}
              placeholder={String(view.capabilities.context_window)}
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </Field>
          <Field label={t.llm.tokenizer}>
            <input
              value={form.tokenizer ?? ""}
              onChange={(e) => setForm({ ...form, tokenizer: e.target.value })}
              placeholder={view.capabilities.tokenizer}
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
          </Field>
          <CapabilitySelect
            label={t.llm.supportsVision}
            value={form.supports_vision ?? ""}
            inherited={view.capabilities.supports_vision}
            onChange={(value) => setForm({ ...form, supports_vision: value })}
          />
          <CapabilitySelect
            label={t.llm.supportsTools}
            value={form.supports_tools ?? ""}
            inherited={view.capabilities.supports_tools}
            onChange={(value) => setForm({ ...form, supports_tools: value })}
          />
          <CapabilitySelect
            label={t.llm.supportsTemperature}
            value={form.supports_temperature ?? ""}
            inherited={view.capabilities.supports_temperature}
            onChange={(value) => setForm({ ...form, supports_temperature: value })}
          />
          <Field label={t.llm.tokenLimitParam}>
            <select
              value={form.token_limit_param ?? ""}
              onChange={(e) => setForm({ ...form, token_limit_param: e.target.value })}
              className="w-full rounded border border-border bg-bg-base px-2 py-1 text-sm"
            >
              <option value="">{view.capabilities.token_limit_param}</option>
              <option value="max_tokens">max_tokens</option>
              <option value="max_completion_tokens">max_completion_tokens</option>
            </select>
          </Field>
          <Field label={t.llm.apiKey}>
            <input
              type="password"
              value={form.api_key ?? ""}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder={
                view.api_key_set
                  ? t.common.setValue(view.api_key ?? "")
                  : t.common.unset
              }
              className="w-full rounded border border-border bg-bg-base px-2 py-1 font-mono text-sm"
            />
            <p className="mt-1 text-xs text-fg-subtle">
              {t.llm.keepKeyHint}
            </p>
          </Field>

          {err && (
            <p className="rounded bg-danger/10 px-2 py-1 text-xs text-danger">
              {err}
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            <button
              onClick={reset}
              disabled={saving || overrideCount === 0}
              className="flex items-center gap-1 text-xs text-fg-subtle hover:text-fg-base disabled:opacity-40"
            >
              <RotateCcw size={11} /> {t.llm.reset}
            </button>
            <button
              onClick={save}
              disabled={!dirty || saving}
              className={cn(
                "flex items-center gap-1.5 rounded bg-accent px-3 py-1 text-xs font-medium text-accent-fg",
                "hover:opacity-90 disabled:opacity-40",
              )}
            >
              {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
              {t.common.save}
            </button>
          </div>
          {savedAt && !saving && (
            <p className="text-right text-xs text-fg-subtle">
              {t.common.saved} · {new Date(savedAt).toLocaleTimeString()}
            </p>
          )}
          {healed > 0 && !saving && (
            <p className="text-right text-xs text-accent">
              {t.llm.reprocessedFailed(healed)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-fg-muted">{label}</span>
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
        className="w-full rounded border border-border bg-bg-base px-2 py-1 text-sm"
      >
        <option value="">{String(inherited)}</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    </Field>
  );
}
