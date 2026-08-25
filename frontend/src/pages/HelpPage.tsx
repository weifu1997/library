/** Help & Documentation page — Linear / Apple HIG modern aesthetic.
 *
 *  - Sub-navigation Tabs: Quick Start, FAQ, Settings Reference, All.
 *  - Quick start interactive journey cards (Settings -> Library -> Chat -> Search).
 *  - Frequently Asked Questions accordion list.
 *  - Complete Configuration & Environment variable reference tables with category filter.
 */
import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import {
  BookOpen,
  MessageSquare,
  Search,
  Settings,
  HelpCircle,
  Sparkles,
  ChevronDown,
  ArrowRight,
  Layers,
  Network,
  Sliders,
  Cpu,
  Database,
  Server,
} from "lucide-react";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type HelpTab = "quickstart" | "faq" | "reference" | "all";

interface ReferenceRowData {
  setting: string;
  meaning: string;
  recommended: string;
}

interface ReferenceGroupData {
  id: string;
  title: string;
  icon: React.ElementType;
  description: string;
  rows: ReferenceRowData[];
}

export function HelpPage() {
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") as HelpTab | null;
  const [activeTab, setActiveTab] = useState<HelpTab>(() => {
    if (tabParam && ["quickstart", "faq", "reference", "all"].includes(tabParam)) {
      return tabParam;
    }
    return "quickstart";
  });

  const [refCategory, setRefCategory] = useState<string>("all");

  const handleTabChange = (tab: HelpTab) => {
    setActiveTab(tab);
    if (tab === "quickstart") {
      searchParams.delete("tab");
      setSearchParams(searchParams, { replace: true });
    } else {
      searchParams.set("tab", tab);
      setSearchParams(searchParams, { replace: true });
    }
  };

  const tabs: { id: HelpTab; label: string; icon: React.ElementType }[] = [
    { id: "quickstart", label: t.help.tabQuickStart, icon: Sparkles },
    { id: "faq", label: t.help.tabFaq, icon: HelpCircle },
    { id: "reference", label: t.help.tabReference, icon: BookOpen },
    { id: "all", label: t.help.tabAll, icon: Layers },
  ];

  const groups = settingsReferenceGroups(t);
  const filteredGroups =
    refCategory === "all"
      ? groups
      : groups.filter((g) => g.id === refCategory);

  return (
    <div className="h-full overflow-y-auto px-6 py-8 select-none">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Page Header */}
        <header className="flex flex-col gap-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-fg-base">
              {t.help.title}
            </h1>
            <span className="rounded-full bg-accent/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent border border-accent/20">
              Guide
            </span>
          </div>
          <p className="text-xs text-fg-muted max-w-2xl leading-relaxed">
            {t.help.subtitle}
          </p>
        </header>

        {/* Sub-Buttons / Tab Navigation Bar — Apple HIG 44px (h-11) */}
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
                  "flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl px-4 text-xs font-semibold transition-all duration-150 active:scale-95 select-none",
                  active
                    ? "bg-accent text-accent-fg shadow-xs font-bold"
                    : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/70",
                )}
              >
                <Icon
                  size={16}
                  strokeWidth={active ? 2.3 : 1.8}
                  className={cn(active ? "text-accent-fg" : "text-fg-muted")}
                />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Panels */}
        <div className="space-y-6 animate-fade-in">
          {/* Quick Start Cards */}
          {(activeTab === "quickstart" || activeTab === "all") && (
            <section className="rounded-3xl border border-border/80 bg-bg-card p-6 sm:p-7 shadow-xs">
              <div className="flex items-center gap-3 mb-6">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20 shadow-xs">
                  <Sparkles size={17} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-fg-base tracking-tight">
                    {t.help.quickStartTitle}
                  </h2>
                </div>
              </div>

              <div className="grid gap-4.5 sm:grid-cols-2 lg:grid-cols-4">
                <HelpStep
                  index={1}
                  icon={Settings}
                  title={t.help.stepConfigureTitle}
                  body={t.help.stepConfigureBody}
                  to="/settings?tab=llm"
                  action={t.help.openSettings}
                />
                <HelpStep
                  index={2}
                  icon={BookOpen}
                  title={t.help.stepImportTitle}
                  body={t.help.stepImportBody}
                  to="/library"
                  action={t.help.openLibrary}
                />
                <HelpStep
                  index={3}
                  icon={MessageSquare}
                  title={t.help.stepAskTitle}
                  body={t.help.stepAskBody}
                  to="/chat"
                  action={t.help.openChat}
                />
                <HelpStep
                  index={4}
                  icon={Search}
                  title={t.help.stepSearchTitle}
                  body={t.help.stepSearchBody}
                  to="/search"
                  action={t.help.openSearch}
                />
              </div>
            </section>
          )}

          {/* FAQ Section */}
          {(activeTab === "faq" || activeTab === "all") && (
            <section className="rounded-3xl border border-border/80 bg-bg-card p-6 sm:p-7 shadow-xs">
              <div className="flex items-center gap-3 mb-6">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20 shadow-xs">
                  <HelpCircle size={17} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-fg-base tracking-tight">
                    {t.help.faqTitle}
                  </h2>
                </div>
              </div>

              <div className="space-y-3">
                {t.help.faq.map((item) => (
                  <details
                    key={item.q}
                    className="group rounded-2xl border border-border/70 bg-bg-subtle/30 open:bg-bg-subtle/70 transition-colors overflow-hidden"
                  >
                    <summary className="flex min-h-[48px] cursor-pointer items-center justify-between gap-3 px-5 py-3.5 text-xs font-bold text-fg-base select-none">
                      <span>{item.q}</span>
                      <ChevronDown
                        size={16}
                        className="shrink-0 text-fg-muted transition-transform duration-200 group-open:rotate-180 group-open:text-accent"
                      />
                    </summary>
                    <div className="border-t border-border/50 px-5 py-4 text-xs leading-relaxed text-fg-muted">
                      {item.a}
                    </div>
                  </details>
                ))}
              </div>
            </section>
          )}

          {/* Settings Reference Section */}
          {(activeTab === "reference" || activeTab === "all") && (
            <section className="rounded-3xl border border-border/80 bg-bg-card p-6 sm:p-7 shadow-xs">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20 shadow-xs">
                  <BookOpen size={17} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-fg-base tracking-tight">
                    {t.help.referenceTitle}
                  </h2>
                </div>
              </div>
              <p className="text-xs text-fg-subtle mb-5 pl-12">
                {t.help.referenceSubtitle}
              </p>

              {/* Sub-Category Filter Buttons (44px height for touch comfort) */}
              <div className="mb-6 flex flex-wrap gap-2 rounded-2xl border border-border/60 bg-bg-subtle/40 p-2">
                <button
                  type="button"
                  onClick={() => setRefCategory("all")}
                  className={cn(
                    "flex h-11 items-center gap-1.5 rounded-xl px-4 text-xs font-semibold transition-all active:scale-95 select-none",
                    refCategory === "all"
                      ? "bg-accent text-accent-fg shadow-xs font-bold"
                      : "text-fg-muted hover:text-fg-base hover:bg-bg-card",
                  )}
                >
                  <Layers size={14} />
                  <span>{t.help.referenceAll}</span>
                </button>
                {groups.map((group) => {
                  const active = refCategory === group.id;
                  const Icon = group.icon;
                  return (
                    <button
                      key={group.id}
                      type="button"
                      onClick={() => setRefCategory(group.id)}
                      className={cn(
                        "flex h-11 items-center gap-1.5 rounded-xl px-4 text-xs font-semibold transition-all active:scale-95 select-none",
                        active
                          ? "bg-accent text-accent-fg shadow-xs font-bold"
                          : "text-fg-muted hover:text-fg-base hover:bg-bg-card",
                      )}
                    >
                      <Icon size={14} />
                      <span>{group.title}</span>
                    </button>
                  );
                })}
              </div>

              {/* Reference Tables */}
              <div className="space-y-3.5">
                {filteredGroups.map((group, index) => (
                  <details
                    key={group.title}
                    open={refCategory !== "all" || index === 0}
                    className="group rounded-2xl border border-border/70 bg-bg-subtle/30 open:bg-bg-subtle/50 transition-colors overflow-hidden"
                  >
                    <summary className="flex min-h-[50px] cursor-pointer items-center justify-between gap-3 px-5 py-3.5 text-xs font-bold text-fg-base select-none">
                      <div className="flex items-center gap-2.5">
                        <group.icon size={15} className="text-accent" />
                        <span>{group.title}</span>
                      </div>
                      <ChevronDown
                        size={16}
                        className="shrink-0 text-fg-muted transition-transform duration-200 group-open:rotate-180 group-open:text-accent"
                      />
                    </summary>
                    <div className="border-t border-border/60 p-5">
                      <p className="mb-4 text-xs text-fg-subtle leading-relaxed">
                        {group.description}
                      </p>
                      <div className="overflow-x-auto rounded-xl border border-border/70 bg-bg-card shadow-xs">
                        <table className="w-full min-w-[34rem] border-collapse text-left text-xs">
                          <thead>
                            <tr className="border-b border-border/70 bg-bg-subtle/60 text-fg-muted text-[11px]">
                              <th className="w-44 py-3 px-4 font-bold">
                                {t.help.referenceSetting}
                              </th>
                              <th className="py-3 px-4 font-bold">
                                {t.help.referenceMeaning}
                              </th>
                              <th className="w-64 py-3 px-4 font-bold">
                                {t.help.referenceRecommended}
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/40">
                            {group.rows.map((row) => (
                              <tr
                                key={row.setting}
                                className="hover:bg-bg-subtle/30 transition-colors"
                              >
                                <td className="py-3.5 px-4 align-top font-semibold text-fg-base">
                                  <span className="rounded-md bg-bg-base px-2 py-1 font-mono text-[11px] border border-border/60">
                                    {row.setting}
                                  </span>
                                </td>
                                <td className="py-3.5 px-4 align-top text-fg-muted leading-relaxed">
                                  {row.meaning}
                                </td>
                                <td className="py-3.5 px-4 align-top text-fg-base/85 leading-relaxed text-[11.5px]">
                                  {row.recommended}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function HelpStep({
  index,
  icon: Icon,
  title,
  body,
  to,
  action,
}: {
  index: number;
  icon: React.ElementType;
  title: string;
  body: string;
  to: string;
  action: string;
}) {
  return (
    <div className="group flex flex-col justify-between rounded-2xl border border-border/80 bg-bg-base/70 p-5 transition-all duration-200 hover:-translate-y-1 hover:border-accent/50 hover:shadow-card hover:bg-bg-card">
      <div>
        {/* Top Icon & Index Row with generous breathing room */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-accent/10 text-accent border border-accent/20 group-hover:scale-105 group-hover:bg-accent group-hover:text-accent-fg transition-all shadow-xs">
            <Icon size={19} />
          </div>
          <span className="inline-flex rounded-full bg-bg-muted/80 px-2.5 py-0.5 text-[11px] font-mono font-bold text-fg-subtle border border-border/50">
            0{index}
          </span>
        </div>

        {/* Content */}
        <h3 className="text-sm font-bold text-fg-base group-hover:text-accent transition-colors tracking-tight">
          {title}
        </h3>
        <p className="mt-2 text-xs text-fg-muted leading-relaxed line-clamp-3 min-h-[52px]">
          {body}
        </p>
      </div>

      {/* Action Button — 44px height (h-11) */}
      <Link
        to={to}
        className="mt-5 inline-flex h-11 items-center justify-between rounded-xl border border-border/80 bg-bg-card px-4 text-xs font-semibold text-fg-base hover:bg-accent hover:text-accent-fg hover:border-accent transition-all shadow-xs active:scale-95"
      >
        <span>{action}</span>
        <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
      </Link>
    </div>
  );
}

function settingsReferenceGroups(
  t: ReturnType<typeof useI18n>["t"],
): ReferenceGroupData[] {
  const r = t.help.reference;
  return [
    {
      id: "connection",
      title: r.connectionTitle,
      icon: Network,
      description: r.connectionDescription,
      rows: [
        row(t.settings.apiBaseUrl, r.apiBaseUrlMeaning, r.apiBaseUrlRecommended),
        row(t.settings.apiToken, r.apiTokenMeaning, r.apiTokenRecommended),
      ],
    },
    {
      id: "preferences",
      title: r.preferencesTitle,
      icon: Sliders,
      description: r.preferencesDescription,
      rows: [
        row(t.settings.language, r.languageMeaning, r.languageRecommended),
        row(t.settings.theme, r.themeMeaning, r.themeRecommended),
        row(t.settings.conflictPolicy, r.conflictMeaning, r.conflictRecommended),
        row(t.settings.agentTokenBudget, r.agentTokenMeaning, r.agentTokenRecommended),
        row(t.settings.executeTurnBudget, r.executeTurnsMeaning, r.executeTurnsRecommended),
        row(t.settings.compression, r.compressionMeaning, r.compressionRecommended),
        row(t.settings.concurrentIngest, r.concurrentIngestMeaning, r.concurrentIngestRecommended),
        row(t.settings.ingestLlmConcurrency, r.ingestConcurrencyMeaning, r.ingestConcurrencyRecommended),
        row(t.settings.statusRefresh, r.statusRefreshMeaning, r.statusRefreshRecommended),
        row(t.settings.compactSidebar, r.compactSidebarMeaning, r.compactSidebarRecommended),
      ],
    },
    {
      id: "llm",
      title: r.llmTitle,
      icon: Cpu,
      description: r.llmDescription,
      rows: [
        row(r.defaultProfile, r.defaultProfileMeaning, r.defaultProfileRecommended),
        row(r.chatProfile, r.chatProfileMeaning, r.chatProfileRecommended),
        row(r.reflectProfile, r.reflectProfileMeaning, r.reflectProfileRecommended),
        row(r.ingestProfile, r.ingestProfileMeaning, r.ingestProfileRecommended),
        row(r.visionProfile, r.visionProfileMeaning, r.visionProfileRecommended),
        row(t.llm.provider, r.providerMeaning, r.providerRecommended),
        row(t.llm.model, r.modelMeaning, r.modelRecommended),
        row(t.llm.baseUrl, r.baseUrlMeaning, r.baseUrlRecommended),
        row(t.llm.apiKey, r.apiKeyMeaning, r.apiKeyRecommended),
      ],
    },
    {
      id: "embedding",
      title: r.embeddingTitle,
      icon: Database,
      description: r.embeddingDescription,
      rows: [
        row(t.settings.semanticRecall, r.semanticRecallMeaning, r.semanticRecallRecommended),
        row(t.settings.embeddingProvider, r.embeddingProviderMeaning, r.embeddingProviderRecommended),
        row(t.settings.embeddingApiKey, r.embeddingApiKeyMeaning, r.embeddingApiKeyRecommended),
        row(t.settings.embeddingBaseUrl, r.embeddingBaseUrlMeaning, r.embeddingBaseUrlRecommended),
        row(t.settings.embeddingModel, r.embeddingModelMeaning, r.embeddingModelRecommended),
        row(t.settings.embeddingDimensions, r.embeddingDimensionsMeaning, r.embeddingDimensionsRecommended),
        row(t.settings.embeddingBatchSize, r.embeddingBatchSizeMeaning, r.embeddingBatchSizeRecommended),
        row(t.settings.semanticRecallLimit, r.semanticRecallLimitMeaning, r.semanticRecallLimitRecommended),
        row(t.settings.semanticIndexBackend, r.semanticIndexBackendMeaning, r.semanticIndexBackendRecommended),
        row(t.settings.semanticIndex, r.semanticIndexMeaning, r.semanticIndexRecommended),
      ],
    },
    {
      id: "rerank",
      title: r.rerankTitle,
      icon: Database,
      description: r.rerankDescription,
      rows: [
        row(t.settings.rerankEnabled, r.rerankMeaning, r.rerankRecommended),
        row(t.settings.rerankApiKey, r.rerankApiKeyMeaning, r.rerankApiKeyRecommended),
        row(t.settings.rerankBaseUrl, r.rerankBaseUrlMeaning, r.rerankBaseUrlRecommended),
        row(t.settings.rerankModel, r.rerankModelMeaning, r.rerankModelRecommended),
        row(t.settings.rerankTopN, r.rerankTopNMeaning, r.rerankTopNRecommended),
        row(t.settings.rerankMaxDocChars, r.rerankDocCharsMeaning, r.rerankDocCharsRecommended),
        row(t.settings.rerankConcurrency, r.rerankConcurrencyMeaning, r.rerankConcurrencyRecommended),
        row(t.settings.evidenceSelection, r.evidenceSelectionMeaning, r.evidenceSelectionRecommended),
      ],
    },
    {
      id: "server",
      title: r.serverStatusTitle,
      icon: Server,
      description: r.serverStatusDescription,
      rows: [
        row(t.settings.kv.home, r.homeMeaning, r.homeRecommended),
        row(t.settings.kv.db, r.dbMeaning, r.dbRecommended),
        row(t.settings.kv.storage, r.storageMeaning, r.storageRecommended),
        row(t.settings.kv.worker, r.workerMeaning, r.workerRecommended),
        row(t.settings.kv.autoLifecycle, r.autoLifecycleMeaning, r.autoLifecycleRecommended),
        row(t.settings.kv.vision, r.visionStatusMeaning, r.visionStatusRecommended),
      ],
    },
  ];
}

function row(setting: string, meaning: string, recommended: string): ReferenceRowData {
  return { setting, meaning, recommended };
}
