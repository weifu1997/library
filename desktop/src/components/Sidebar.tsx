import { NavLink } from "react-router-dom";
import {
  BookOpen,
  CircleHelp,
  Info,
  LayoutDashboard,
  MessageSquare,
  Search,
  Settings,
  Library,
} from "lucide-react";

import { APP_VERSION } from "@/lib/appVersion";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/lib/prefs";
import { useI18n } from "@/lib/i18n";

interface Item {
  to: string;
  labelKey: "overview" | "chat" | "library" | "search" | "settings" | "help" | "about";
  icon: typeof MessageSquare;
}

const ITEMS: Item[] = [
  { to: "/overview", labelKey: "overview", icon: LayoutDashboard },
  { to: "/chat", labelKey: "chat", icon: MessageSquare },
  { to: "/library", labelKey: "library", icon: BookOpen },
  { to: "/search", labelKey: "search", icon: Search },
  { to: "/settings", labelKey: "settings", icon: Settings },
  { to: "/help", labelKey: "help", icon: CircleHelp },
  { to: "/about", labelKey: "about", icon: Info },
];

export function Sidebar() {
  const compact = usePrefs((s) => s.compactSidebar);
  const { t } = useI18n();

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-border/80 bg-bg-subtle/95 select-none transition-all duration-200 ease-out",
        compact ? "w-[72px]" : "w-64",
      )}
    >
      {/* Brand Header */}
      <div
        className={cn(
          "flex items-center gap-3.5 h-16 border-b border-border/60",
          compact ? "justify-center px-2" : "px-5",
        )}
      >
        <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-500/25 ring-1 ring-white/20">
          <Library size={20} strokeWidth={2.2} className="drop-shadow-xs" />
          <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60"></span>
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-bg-subtle"></span>
          </span>
        </div>
        {!compact && (
          <div className="flex flex-col min-w-0 leading-tight">
            <span className="text-[15px] font-bold tracking-tight text-fg-base truncate">
              {t.common.appName}
            </span>
            <span className="text-[11px] font-medium text-fg-subtle truncate">
              {t.common.personalLibrary}
            </span>
          </div>
        )}
      </div>

      {/* Navigation Links — Apple HIG standard min 44px height */}
      <nav className="flex flex-col gap-1.5 px-3 py-4">
        {ITEMS.map((it) => {
          const Icon = it.icon;
          const label = t.nav[it.labelKey];
          return (
            <NavLink
              key={it.to}
              to={it.to}
              title={compact ? label : undefined}
              className={({ isActive }) =>
                cn(
                  "group relative flex items-center rounded-xl text-sm font-semibold transition-all duration-150 active:scale-[0.98]",
                  compact
                    ? "justify-center h-11 w-11 mx-auto"
                    : "h-11 gap-3 px-3.5",
                  isActive
                    ? "bg-bg-elevated text-fg-base shadow-xs ring-1 ring-border/80"
                    : "text-fg-muted hover:bg-bg-muted/70 hover:text-fg-base",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      className={cn(
                        "absolute rounded-full bg-accent transition-all duration-200",
                        compact
                          ? "bottom-1 left-1/2 -translate-x-1/2 h-1 w-4"
                          : "left-1.5 top-1/2 -translate-y-1/2 h-5 w-1",
                      )}
                    />
                  )}
                  <Icon
                    size={19}
                    strokeWidth={isActive ? 2.3 : 1.9}
                    className={cn(
                      "transition-colors shrink-0",
                      isActive
                        ? "text-accent"
                        : "text-fg-subtle group-hover:text-fg-base",
                    )}
                  />
                  {!compact && <span className="truncate">{label}</span>}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Footer Version Tag */}
      {!compact && (
        <div className="mt-auto border-t border-border/60 px-5 py-3.5 flex items-center justify-between text-[11px] text-fg-subtle">
          <span className="font-mono font-medium tracking-tight opacity-80">v{APP_VERSION}</span>
          <span className="flex h-2 w-2 rounded-full bg-emerald-500"></span>
        </div>
      )}
    </aside>
  );
}
