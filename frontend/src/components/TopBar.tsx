import { useLocation } from "react-router-dom";
import { Moon, Sun, MonitorSmartphone, MessageSquare, BookOpen, Search, Settings, CircleHelp, Info } from "lucide-react";

import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export function TopBar() {
  const { mode, setMode } = useTheme();
  const { t } = useI18n();
  const location = useLocation();

  const getPageInfo = () => {
    const path = location.pathname;
    if (path.startsWith("/chat")) return { title: t.nav.chat, icon: MessageSquare };
    if (path.startsWith("/library")) return { title: t.nav.library, icon: BookOpen };
    if (path.startsWith("/search")) return { title: t.nav.search, icon: Search };
    if (path.startsWith("/settings")) return { title: t.nav.settings, icon: Settings };
    if (path.startsWith("/help")) return { title: t.nav.help, icon: CircleHelp };
    if (path.startsWith("/about")) return { title: t.nav.about, icon: Info };
    return { title: t.common.appName, icon: BookOpen };
  };

  const page = getPageInfo();
  const PageIcon = page.icon;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/80 bg-bg-base/85 px-6 backdrop-blur-md transition-colors select-none z-10">
      {/* Breadcrumb / Page Title */}
      <div className="flex items-center gap-2.5 text-sm font-semibold text-fg-base">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10 text-accent border border-accent/20">
          <PageIcon size={16} strokeWidth={2.2} />
        </div>
        <span className="font-bold tracking-tight text-[14px]">{page.title}</span>
      </div>

      {/* Segmented Theme Switcher — generous 34px buttons with 44px hit area */}
      <div className="flex items-center gap-1 rounded-xl border border-border/80 bg-bg-subtle p-1 shadow-xs">
        <ThemeBtn current={mode} mode="light" title={t.theme.light} onClick={() => setMode("light")}>
          <Sun size={15} strokeWidth={2} />
        </ThemeBtn>
        <ThemeBtn current={mode} mode="system" title={t.theme.system} onClick={() => setMode("system")}>
          <MonitorSmartphone size={15} strokeWidth={2} />
        </ThemeBtn>
        <ThemeBtn current={mode} mode="dark" title={t.theme.dark} onClick={() => setMode("dark")}>
          <Moon size={15} strokeWidth={2} />
        </ThemeBtn>
      </div>
    </header>
  );
}

function ThemeBtn({
  current,
  mode,
  title,
  onClick,
  children,
}: {
  current: string;
  mode: string;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const active = current === mode;
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition-all duration-150 active:scale-95",
        active
          ? "bg-bg-elevated text-accent shadow-xs ring-1 ring-border/80"
          : "text-fg-subtle hover:text-fg-base hover:bg-bg-muted/60",
      )}
      title={title}
      type="button"
    >
      {children}
    </button>
  );
}
