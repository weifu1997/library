import { lazy, Suspense, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import { BackendGate } from "@/components/BackendGate";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { StatusBar } from "@/components/StatusBar";
import { ViewerLoading } from "@/components/library/viewers/ViewerShared";
import { ChatPage } from "@/pages/ChatPage";
import { useTheme } from "@/lib/theme";

// Non-chat pages are code-split on demand so the initial /chat route stays
// light; ChatPage itself stays in the main chunk since it's the landing route.
const LibraryPage = lazy(() =>
  import("@/pages/LibraryPage").then((m) => ({ default: m.LibraryPage })),
);
const SearchPage = lazy(() =>
  import("@/pages/SearchPage").then((m) => ({ default: m.SearchPage })),
);
const OverviewPage = lazy(() =>
  import("@/pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const HelpPage = lazy(() =>
  import("@/pages/HelpPage").then((m) => ({ default: m.HelpPage })),
);
const AboutPage = lazy(() =>
  import("@/pages/AboutPage").then((m) => ({ default: m.AboutPage })),
);

export default function App() {
  const initTheme = useTheme((s) => s.init);

  useEffect(() => {
    return initTheme();
  }, [initTheme]);

  return (
    <BackendGate>
      <div className="flex h-full w-full flex-col bg-bg-base text-fg-base">
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <TopBar />
            <main className="min-h-0 flex-1 overflow-hidden">
              {/* A lazy chunk failing to load or a page throwing mid-render
                  must not blank the pane — ErrorBoundary shows a reload
                  affordance instead. */}
              <ErrorBoundary>
                <Suspense fallback={<ViewerLoading />}>
                <Routes>
                  <Route path="/" element={<Navigate to="/chat" replace />} />
                  <Route path="/library/*" element={<LibraryPage />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/overview" element={<OverviewPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/help" element={<HelpPage />} />
                  <Route path="/about" element={<AboutPage />} />
                  {/* Safety net: stray hash fragments (e.g. an unresolved
                      in-answer "#foo" anchor) must not blank the pane. */}
                  <Route path="*" element={<Navigate to="/chat" replace />} />
                </Routes>
                </Suspense>
              </ErrorBoundary>
            </main>
          </div>
        </div>
        <StatusBar />
      </div>
    </BackendGate>
  );
}
