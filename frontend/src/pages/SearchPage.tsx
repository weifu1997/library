import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search as SearchIcon, FileText, Loader2, X, Sparkles, Folder, ArrowRight } from "lucide-react";

import { search } from "@/api/client";
import type { SearchEntry } from "@/types/api";
import { useI18n } from "@/lib/i18n";

export function SearchPage() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { t } = useI18n();

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const handle = window.setTimeout(async () => {
      try {
        const r = await search.query(term, 25);
        if (!cancelled) setResults(r.entries);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [q]);

  const clearSearch = () => {
    setQ("");
    setResults(null);
    setError(null);
    inputRef.current?.focus();
  };

  const sampleQueries = ["PDF", "架构", "设计", "API", "文档", "知识库"];

  return (
    <div className="flex h-full flex-col select-none bg-bg-base">
      {/* Search Header Container — 52px search input */}
      <div className="border-b border-border/80 bg-bg-subtle/80 px-6 py-5 backdrop-blur-md">
        <div className="mx-auto flex h-[52px] max-w-3xl items-center gap-3 rounded-2xl border border-border/90 bg-bg-card px-4.5 shadow-card focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 transition-all">
          <SearchIcon size={18} className="text-fg-subtle shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.search.placeholder}
            className="flex-1 bg-transparent text-sm font-medium text-fg-base outline-none placeholder:text-fg-subtle selectable"
          />
          {q && (
            <button
              onClick={clearSearch}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-fg-subtle hover:bg-bg-muted hover:text-fg-base active:scale-95 transition-all"
              type="button"
            >
              <X size={15} />
            </button>
          )}
          {loading && <Loader2 size={16} className="animate-spin text-accent shrink-0" />}
          <span className="hidden sm:inline-flex rounded-lg border border-border/80 bg-bg-muted px-2 py-0.5 text-xs font-mono text-fg-subtle">
            /
          </span>
        </div>
      </div>

      {/* Search Results Area */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-3xl space-y-5">
          {error && (
            <div className="rounded-2xl border border-danger/30 bg-danger-subtle/90 p-4.5 text-xs text-danger shadow-sm">
              {error}
            </div>
          )}

          {/* Empty State / Search Suggestions */}
          {results === null && !error && !loading && (
            <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-card text-accent border border-border/80 shadow-xs">
                <SearchIcon size={24} strokeWidth={2} />
              </div>
              <p className="text-sm font-bold text-fg-base">{t.search.empty}</p>
              <p className="mt-1.5 max-w-sm text-xs text-fg-muted leading-relaxed">
                输入关键词、文件名或特定标签检索资料库中的全部知识点。
              </p>

              {/* Sample Queries Chips */}
              <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                {sampleQueries.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => setQ(tag)}
                    className="inline-flex h-9 items-center px-4 gap-1.5 rounded-full border border-border/80 bg-bg-card px-3.5 text-xs font-medium text-fg-muted hover:border-accent/50 hover:text-accent hover:bg-bg-subtle active:scale-95 transition-all shadow-xs"
                  >
                    <span>#</span>
                    <span>{tag}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* No Matches Found */}
          {results && results.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-card text-fg-subtle border border-border/80 shadow-xs">
                <Sparkles size={24} strokeWidth={1.8} />
              </div>
              <p className="text-sm font-bold text-fg-base">{t.search.noMatches}</p>
              <p className="mt-1.5 text-xs text-fg-muted">请尝试其他关键词或缩短搜索词。</p>
            </div>
          )}

          {/* Search Results List */}
          {results && results.length > 0 && (
            <div className="space-y-3 animate-fade-in">
              <div className="text-xs font-semibold text-fg-muted px-1">
                找到 {results.length} 条相关结果
              </div>
              {results.map((e) => (
                <Link
                  to={`/library?entry=${encodeURIComponent(e.entry_id)}`}
                  key={e.entry_id}
                  className="group block rounded-2xl border border-border/80 bg-bg-card p-5 shadow-xs hover:border-accent/60 hover:bg-bg-elevated hover:shadow-card transition-all duration-150 active:scale-[0.99]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20">
                        <FileText size={16} />
                      </div>
                      <span className="truncate font-bold text-sm text-fg-base group-hover:text-accent transition-colors">
                        {e.display_name}
                      </span>
                    </div>
                    <ArrowRight size={15} className="shrink-0 text-accent opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                  </div>

                  {e.folder_path && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs font-mono text-fg-subtle">
                      <Folder size={12} className="shrink-0" />
                      <span className="truncate">{e.folder_path}</span>
                    </div>
                  )}

                  {e.summary && (
                    <p className="mt-2.5 line-clamp-2 text-xs text-fg-muted leading-relaxed">
                      {e.summary}
                    </p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
