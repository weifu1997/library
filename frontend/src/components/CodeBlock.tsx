/** Lazy-loaded syntax highlighter for fenced code blocks.
 *
 *  react-syntax-highlighter + its Prism styles are the single heaviest
 *  dependency in the markdown stack (well over half of what MarkdownView
 *  pulls into the main bundle). They are only needed when a fenced block
 *  actually renders, so we dynamic-import them on first use instead of
 *  statically importing them from MarkdownView.
 *
 *  The copy-button header renders immediately; the highlighted body fills
 *  in when the chunk arrives, with the raw text shown in the meantime so
 *  the user never stares at a blank box. */
import { useEffect, useState } from "react";
import type { ComponentType } from "react";
import { Check, Copy } from "lucide-react";

import { useTheme } from "@/lib/theme";
import { useTemporaryValue } from "@/hooks/useTemporaryValue";
import { useI18n } from "@/lib/i18n";
import type { SyntaxHighlighterProps } from "react-syntax-highlighter";

type PrismStyles = typeof import("react-syntax-highlighter/dist/esm/styles/prism");

/** The highlighter component + the style pair, resolved asynchronously.
 *  `Prism` is a React component type; the styles object is keyed by theme. */
interface LoadedHighlighter {
  Prism: ComponentType<SyntaxHighlighterProps>;
  styles: PrismStyles;
}

export function CodeBlock({ language, text }: { language: string; text: string }) {
  const { effective } = useTheme();
  const { t } = useI18n();
  const [copied, setCopied] = useTemporaryValue(false, 1500);
  const [hl, setHl] = useState<LoadedHighlighter | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Both resolve in parallel; each becomes its own on-demand chunk.
    Promise.all([
      import("react-syntax-highlighter"),
      import("react-syntax-highlighter/dist/esm/styles/prism"),
    ]).then(([sh, styles]) => {
      if (!cancelled) setHl({ Prism: sh.Prism, styles });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch { /* ignore — non-secure context, clipboard blocked, etc. */ }
  };

  const style = hl?.styles[effective === "dark" ? "vscDarkPlus" : "prism"];
  const SyntaxHighlighter = hl?.Prism;

  return (
    <div className="group relative my-3 overflow-hidden rounded-lg border border-border bg-bg-muted">
      <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3 py-1 text-[11px] text-fg-subtle">
        <span className="font-mono">{language}</span>
        <button
          onClick={onCopy}
          className="flex h-7 items-center gap-1.5 rounded-lg px-2 text-[11px] font-semibold text-fg-subtle hover:bg-bg-card hover:text-fg-base active:scale-95 transition-all shadow-xs border border-border/50"
          title={t.common.copy}
        >
          {copied
            ? <><Check size={11} /> {t.common.copied}</>
            : <><Copy size={11} /> {t.common.copy}</>}
        </button>
      </div>
      {SyntaxHighlighter && style ? (
        <SyntaxHighlighter
          language={language}
          style={style}
          customStyle={{
            margin: 0,
            padding: "10px 14px",
            fontSize: 12,
            background: "transparent",
          }}
          codeTagProps={{ style: { fontFamily: "inherit" } }}
          wrapLongLines={false}
        >
          {text}
        </SyntaxHighlighter>
      ) : (
        <pre className="overflow-x-auto p-2.5 font-mono text-xs leading-relaxed">
          <code>{text}</code>
        </pre>
      )}
    </div>
  );
}
