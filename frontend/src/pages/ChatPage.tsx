/** Chat workbench — drives the SSE state machine in @/api/chatStream
 *  and renders each frame type as a turn entry:
 *
 *    conversation/plan/thinking → muted progress markers (collapsible)
 *    tool_call/tool_result      → grey blocks with payload preview
 *    answer                     → markdown body + footnote citations
 *    error                      → red banner inline
 *
 *  Layout: left rail with session list, right pane with conversation +
 *  composer.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Gauge,
  Send,
  Square,
  Sparkles,
  X,
  Zap,
  Brain,
  Image as ImageIcon,
  BookOpen,
  Search,
  ArrowRight,
} from "lucide-react";

import { cancelChat, streamChat } from "@/api/chatStream";
import { sessions, settings as settingsApi } from "@/api/client";
import { SessionList } from "@/components/SessionList";
import { TurnView, type Step, type Turn } from "@/components/TurnView";
import { useChatSession } from "@/lib/chatSession";
import { useI18n, type I18nStrings } from "@/lib/i18n";
import { parseUserArtifact, parseUserArtifactEvent } from "@/lib/userArtifact";
import {
  CHAT_IMAGE_MAX_BYTES,
  CHAT_IMAGE_MAX_COUNT,
  cn,
  fileToChatImage,
  formatBytes,
  isSupportedChatImageType,
  type PendingChatImage,
} from "@/lib/utils";
import type {
  ChatEvent,
  ChatImage,
  ChatMode,
  LlmSettings,
  PlanBudgetData,
  ReplayedTurn,
  ThinkingEventData,
  UserArtifact,
} from "@/types/api";

interface LiveStream {
  abort: AbortController;
  generation: number;
  turnIdx: number;
  mode: ChatMode;
  turns: Turn[];
  conversationId?: string;
  pendingCancel?: boolean;
}

const liveStreams = new Map<string, LiveStream>();
let streamGeneration = 0;

export function ChatPage() {
  const sessionId = useChatSession((s) => s.sessionId);
  const setSessionId = useChatSession((s) => s.setSessionId);
  const turns = useChatSession((s) => s.turns);
  const chatMode = useChatSession((s) => s.chatMode);
  const streaming = useChatSession((s) => s.streaming);
  const loading = useChatSession((s) => s.loading);
  const { setTurns, setChatMode, setStreaming, setLoading, reset } = useChatSession();
  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<PendingChatImage[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [imageErr, setImageErr] = useState<string | null>(null);
  const [openErr, setOpenErr] = useState<string | null>(null);
  const [llmReady, setLlmReady] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const { t: i18n } = useI18n();

  useEffect(() => {
    let cancelled = false;
    settingsApi.llm().then(
      (llm) => {
        if (!cancelled) setLlmReady(hasRequiredLlmKeys(llm));
      },
      () => {
        if (!cancelled) setLlmReady(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const ensureSession = useCallback(
    async (initiatingMessage?: string): Promise<string> => {
      const sid = useChatSession.getState().sessionId;
      if (sid) return sid;
      const s = await sessions.open(initiatingMessage);
      setSessionId(s.session_id);
      setRefreshSignal((n) => n + 1);
      return s.session_id;
    },
    [setSessionId, setRefreshSignal],
  );

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns]);

  useEffect(() => {
    const { sessionId } = useChatSession.getState();
    if (!sessionId) return;
    const live = liveStreams.get(sessionId);
    if (live) {
      setTurns(live.turns);
      setChatMode(live.mode);
      setStreaming(true);
      return;
    }
    let cancelled = false;
    setLoading(true);
    sessions
      .messages(sessionId)
      .then((transcript) => {
        if (cancelled) return;
        if (!useChatSession.getState().streaming) {
          setTurns(transcript.turns.map((rt) => replayedToTurn(rt, i18n)));
          setChatMode(transcript.mode ?? inferTranscriptMode(transcript.turns));
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setOpenErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, i18n, setTurns, setChatMode, setStreaming, setLoading]);

  const loadSession = useCallback(
    (id: string) => {
      if (id === sessionId) return;
      setSessionId(id);
      setOpenErr(null);
    },
    [sessionId, setSessionId],
  );

  const newChat = useCallback(() => {
    reset();
    setOpenErr(null);
  }, [reset]);

  const addImageFiles = useCallback(
    async (files: File[]) => {
      const imgs = files.filter((f) => f.type.startsWith("image/"));
      if (imgs.length === 0) return;
      const room = Math.max(0, CHAT_IMAGE_MAX_COUNT - pendingImages.length);
      if (room <= 0) {
        setImageErr(i18n.chat.imageTooMany(CHAT_IMAGE_MAX_COUNT));
        return;
      }
      const toAdd = imgs.slice(0, room);
      setImageErr(null);
      const converted: PendingChatImage[] = [];
      for (const f of toAdd) {
        if (!isSupportedChatImageType(f.type)) {
          setImageErr(i18n.chat.unsupportedImageType);
          continue;
        }
        if (f.size > CHAT_IMAGE_MAX_BYTES) {
          setImageErr(i18n.chat.imageTooLarge(formatBytes(CHAT_IMAGE_MAX_BYTES)));
          continue;
        }
        try {
          converted.push(await fileToChatImage(f));
        } catch {
          setImageErr(i18n.chat.imageReadFailed);
        }
      }
      if (converted.length > 0) {
        setPendingImages((prev) => [...prev, ...converted]);
      }
    },
    [pendingImages.length, i18n],
  );

  const removeImage = useCallback((id: string) => {
    setPendingImages((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }, []);

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = Array.from(e.clipboardData.items);
      const files: File[] = [];
      for (const it of items) {
        if (it.kind === "file" && it.type.startsWith("image/")) {
          const f = it.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length > 0) {
        e.preventDefault();
        void addImageFiles(files);
      }
    },
    [addImageFiles],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const files = Array.from(e.dataTransfer.files);
      void addImageFiles(files);
    },
    [addImageFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const stop = useCallback(() => {
    const { sessionId } = useChatSession.getState();
    if (!sessionId) return;
    const live = liveStreams.get(sessionId);
    if (!live) {
      setStreaming(false);
      return;
    }
    const conversationId =
      live.conversationId ?? live.turns[live.turnIdx]?.conversationId;
    if (conversationId) {
      void cancelChat(conversationId).catch((err: unknown) => {
        console.error(err);
      });
      live.abort.abort();
      liveStreams.delete(sessionId);
      setStreaming(false);
      return;
    }
    // Keep streaming true so Send stays blocked until the conversation
    // event arrives and cancel actually fires.
    live.pendingCancel = true;
  }, [setStreaming]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text && pendingImages.length === 0) return;
    if (useChatSession.getState().streaming) return;

    const imgs: ChatImage[] = pendingImages.map((p) => ({
      media_type: p.media_type,
      data_b64: p.data_b64,
    }));
    setInput("");
    setPendingImages([]);
    setImageErr(null);

    const isFirstTurn = useChatSession.getState().turns.length === 0;
    const sid = await ensureSession(text);

    const turn: Turn = {
      query: text,
      images: imgs.length > 0 ? imgs : undefined,
      steps: [],
      answer: null,
      error: null,
      done: false,
    };
    const nextTurns = [...useChatSession.getState().turns, turn];
    setTurns(nextTurns);
    setStreaming(true);

    const abort = new AbortController();
    const gen = ++streamGeneration;
    const curIdx = nextTurns.length - 1;
    const live: LiveStream = {
      abort,
      generation: gen,
      turnIdx: curIdx,
      mode: chatMode,
      turns: nextTurns,
    };
    liveStreams.set(sid, live);

    try {
      await streamChat(sid, text, {
        signal: abort.signal,
        mode: chatMode,
        images: imgs.length > 0 ? imgs : undefined,
        onEvent: (ev) => {
          const cur = liveStreams.get(sid);
          if (!cur || cur.generation !== gen) return;
          let conversationId = ev.conversationId;
          if (!conversationId && ev.type === "conversation") {
            conversationId = typeof ev.data === "string"
              ? ev.data
              : extractId(ev.data, "conversation_id");
          }
          if (conversationId) cur.conversationId = conversationId;
          cur.turns = applyEventToTurnList(cur.turns, cur.turnIdx, ev, i18n);
          if (cur.pendingCancel && cur.conversationId) {
            void cancelChat(cur.conversationId).catch((err: unknown) => {
              console.error(err);
            });
            cur.abort.abort();
            liveStreams.delete(sid);
            if (useChatSession.getState().sessionId === sid) {
              setTurns(cur.turns);
              setStreaming(false);
            }
            return;
          }
          if (useChatSession.getState().sessionId === sid) {
            setTurns(cur.turns);
            if (!cur.pendingCancel) setStreaming(true);
          }
          if (ev.type === "plan" && extractSessionNameFromPlan(ev.data)) {
            setRefreshSignal((n) => n + 1);
          }
        },
      });
    } catch (e: unknown) {
      if (abort.signal.aborted) return;
      const cur = liveStreams.get(sid);
      if (cur && cur.generation === gen) {
        cur.turns = updateTurn(cur.turns, cur.turnIdx, (t) => ({
          ...finishActiveThinking(t),
          error: e instanceof Error ? e.message : String(e),
          done: true,
        }));
        if (useChatSession.getState().sessionId === sid) {
          setTurns(cur.turns);
        }
      }
    } finally {
      const cur = liveStreams.get(sid);
      if (cur && cur.generation === gen) {
        cur.turns = updateTurn(cur.turns, cur.turnIdx, (t) => ({
          ...finishActiveThinking(t),
          done: true,
        }));
        liveStreams.delete(sid);
        if (useChatSession.getState().sessionId === sid) {
          setTurns(cur.turns);
          setStreaming(false);
        }
      }
      if (cur && cur.generation === gen && isFirstTurn) setRefreshSignal((n) => n + 1);
    }
  }, [input, pendingImages, chatMode, ensureSession, setTurns, setStreaming, i18n]);

  return (
    <div className="flex h-full w-full select-none">
      <SessionList
        activeSessionId={sessionId}
        onSelect={loadSession}
        onNewChat={newChat}
        refreshSignal={refreshSignal}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-bg-base">
        {/* Chat Messages Transcript */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-4xl space-y-6">
            {openErr && (
              <div className="rounded-2xl border border-danger/30 bg-danger-subtle/90 p-4 text-xs text-danger shadow-sm">
                {openErr}
              </div>
            )}
            {loading && (
              <div className="flex items-center justify-center gap-2.5 py-16 text-xs text-fg-subtle">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent"></span>
                <span>{i18n.chat.loadingTranscript}</span>
              </div>
            )}
            {!loading && turns.length === 0 && (
              <ChatEmpty
                t={i18n}
                llmReady={llmReady}
                onSelectPrompt={(p) => {
                  setInput(p);
                }}
              />
            )}
            {turns.map((t, i) => (
              <TurnView key={i} turn={t} />
            ))}
          </div>
        </div>

        {/* Composer Floating Container */}
        <div
          className={cn(
            "border-t border-border/80 bg-bg-subtle/80 px-6 py-4 backdrop-blur-md transition-colors",
            dragOver && "bg-accent-subtle/50 ring-2 ring-accent inset-0",
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="mx-auto max-w-4xl">
            {/* Attached Images Pill Bar */}
            {(pendingImages.length > 0 || imageErr || dragOver) && (
              <div className="mb-3">
                {pendingImages.length > 0 && (
                  <div className="flex flex-wrap gap-2.5 animate-fade-in">
                    {pendingImages.map((img) => (
                      <div
                        key={img.id}
                        className="group relative h-16 w-16 overflow-hidden rounded-xl border border-border/80 bg-bg-elevated shadow-sm"
                      >
                        <img
                          src={img.previewUrl}
                          alt={img.name ?? i18n.chat.imageAlt(1)}
                          className="h-full w-full object-cover"
                        />
                        <button
                          type="button"
                          onClick={() => removeImage(img.id)}
                          title={i18n.chat.removeImage}
                          aria-label={i18n.chat.removeImage}
                          className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur shadow-sm hover:bg-danger transition-colors"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {imageErr && (
                  <div className="mt-1 text-xs font-semibold text-danger">{imageErr}</div>
                )}
                {dragOver && !imageErr && (
                  <div className="mt-1 text-xs font-semibold text-accent animate-pulse">
                    {i18n.chat.dropImagesHere}
                  </div>
                )}
              </div>
            )}

            {/* Input Floating Card */}
            <div className="rounded-2xl border border-border/90 bg-bg-card shadow-card focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 transition-all">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPaste={handlePaste}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                placeholder={i18n.chat.inputPlaceholder}
                rows={1}
                className="w-full resize-none bg-transparent px-5 pt-4 pb-2.5 text-sm text-fg-base outline-none placeholder:text-fg-subtle max-h-48"
              />

              {/* Bottom Action Bar inside composer — All controls unified to 44px (h-11) height standard */}
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3.5 pt-1.5 border-t border-border/40">
                <div className="flex items-center gap-2.5">
                  {/* Mode Selector Segmented Group (44px h-11 container, equal width buttons) */}
                  <div
                    className="grid grid-cols-3 gap-1 h-11 items-center rounded-xl border border-border/80 bg-bg-base/80 p-1 shadow-xs min-w-[270px]"
                    aria-label={i18n.chat.mode}
                    role="group"
                  >
                    <button
                      type="button"
                      title={i18n.chat.autoModeHint}
                      disabled={streaming}
                      onClick={() => setChatMode("auto")}
                      className={cn(
                        "flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all active:scale-95",
                        chatMode === "auto"
                          ? "bg-accent text-accent-fg shadow-xs font-bold"
                          : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/50",
                        streaming && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <Gauge size={14} strokeWidth={2.2} />
                      <span>{i18n.chat.autoMode}</span>
                    </button>
                    <button
                      type="button"
                      title={i18n.chat.quickModeHint}
                      disabled={streaming}
                      onClick={() => setChatMode("quick")}
                      className={cn(
                        "flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all active:scale-95",
                        chatMode === "quick"
                          ? "bg-accent text-accent-fg shadow-xs font-bold"
                          : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/50",
                        streaming && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <Zap size={14} strokeWidth={2.2} />
                      <span>{i18n.chat.quickMode}</span>
                    </button>
                    <button
                      type="button"
                      title={i18n.chat.deepModeHint}
                      disabled={streaming}
                      onClick={() => setChatMode("deep")}
                      className={cn(
                        "flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all active:scale-95",
                        chatMode === "deep"
                          ? "bg-accent text-accent-fg shadow-xs font-bold"
                          : "text-fg-muted hover:text-fg-base hover:bg-bg-subtle/50",
                        streaming && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <Sparkles size={14} strokeWidth={2.2} />
                      <span>{i18n.chat.deepMode}</span>
                    </button>
                  </div>

                  {/* Image Attachment Button — 44px h-11 standard */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files) void addImageFiles(Array.from(e.target.files));
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    title={i18n.chat.dropImagesHere}
                    className="flex h-11 w-11 items-center justify-center rounded-xl border border-border/80 bg-bg-base/80 text-fg-muted hover:bg-bg-subtle hover:text-fg-base hover:border-border active:scale-95 transition-all shadow-xs"
                  >
                    <ImageIcon size={17} />
                  </button>
                </div>

                {/* Send / Stop Action Button — 44px h-11 standard */}
                <div className="flex items-center gap-2">
                  {streaming ? (
                    <button
                      type="button"
                      onClick={stop}
                      className="flex h-11 items-center gap-2 rounded-xl bg-danger/10 text-danger border border-danger/30 px-5 text-xs font-semibold hover:bg-danger hover:text-white active:scale-95 transition-all shadow-xs"
                    >
                      <Square size={13} fill="currentColor" />
                      <span>{i18n.chat.stop}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void send()}
                      disabled={(!input.trim() && pendingImages.length === 0) || loading}
                      className={cn(
                        "flex h-11 items-center gap-2 rounded-xl px-5 text-xs font-semibold transition-all active:scale-95 shadow-sm",
                        (input.trim() || pendingImages.length > 0) && !loading
                          ? "bg-accent text-accent-fg hover:bg-accent-hover shadow-indigo-500/25 hover:brightness-105"
                          : "cursor-not-allowed bg-bg-muted text-fg-subtle opacity-70",
                      )}
                    >
                      <Send size={14} strokeWidth={2.4} />
                      <span>{i18n.chat.send}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Session Indicator */}
            <div className="mt-2 flex items-center justify-between px-1.5 text-[11px] text-fg-subtle">
              <span>
                {sessionId ? (
                  <>
                    {i18n.chat.session} <span className="font-mono text-fg-muted font-medium">{sessionId.slice(0, 8)}...</span>
                  </>
                ) : (
                  i18n.chat.sessionOpens
                )}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatEmpty({
  t,
  llmReady,
  onSelectPrompt,
}: {
  t: I18nStrings;
  llmReady: boolean | null;
  onSelectPrompt?: (prompt: string) => void;
}) {
  // Card copy lives in i18n (chat.suggestions); icons stay component-side,
  // matched by position.
  const suggestionIcons = [BookOpen, Search, Brain];
  const suggestions = t.chat.suggestions.map((s, idx) => ({
    ...s,
    icon: suggestionIcons[idx] ?? Sparkles,
  }));

  return (
    <div className="flex h-full min-h-[50vh] flex-col items-center justify-center text-center animate-fade-in px-4 py-8">
      {/* Brand Hero Glow */}
      <div className="relative mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-500 text-white shadow-xl shadow-indigo-500/25 ring-1 ring-white/20">
        <Sparkles size={30} strokeWidth={2.2} />
        <span className="absolute -inset-1 rounded-2xl bg-indigo-500/20 blur-md animate-pulse-glow"></span>
      </div>

      <h2 className="text-2xl font-bold tracking-tight text-fg-base">{t.chat.emptyTitle}</h2>
      <p className="mt-2 max-w-md text-xs sm:text-sm text-fg-muted leading-relaxed">
        {t.chat.emptyBody}
      </p>

      {/* LLM Missing Warning */}
      {llmReady === false && (
        <div className="mt-6 max-w-lg rounded-2xl border border-danger/30 bg-danger-subtle/90 p-4.5 text-left text-xs shadow-sm">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
            <div className="flex-1">
              <div className="font-bold text-danger text-sm">{t.chat.llmMissingTitle}</div>
              <p className="mt-1 text-fg-muted leading-normal">{t.chat.llmMissingBody}</p>
              <Link
                to="/settings?tab=llm"
                className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-accent-fg hover:bg-accent-hover transition-colors shadow-xs active:scale-95"
              >
                <span>{t.chat.llmMissingAction}</span>
                <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Prompt Suggestion Cards */}
      <div className="mt-8 grid w-full max-w-2xl gap-3.5 sm:grid-cols-3 text-left">
        {suggestions.map((s, idx) => {
          const Icon = s.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt?.(s.prompt)}
              className="group flex flex-col justify-between rounded-2xl border border-border/80 bg-bg-card p-4 transition-all duration-200 hover:-translate-y-1 hover:border-accent/50 hover:shadow-md active:scale-[0.98]"
            >
              <div className="space-y-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20 group-hover:scale-105 transition-transform">
                  <Icon size={16} />
                </div>
                <div>
                  <div className="text-xs font-bold text-fg-base group-hover:text-accent transition-colors">
                    {s.title}
                  </div>
                  <div className="mt-1 text-[11px] text-fg-subtle leading-relaxed line-clamp-2">
                    {s.desc}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-end text-accent opacity-0 group-hover:opacity-100 transition-opacity">
                <ArrowRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function hasRequiredLlmKeys(llm: LlmSettings): boolean {
  return (["chat", "reflect", "ingest"] as const).every(
    (profile) => Boolean(llm.profiles[profile]?.api_key_set),
  );
}

function updateTurn(prev: Turn[], idx: number, fn: (t: Turn) => Turn): Turn[] {
  const next = [...prev];
  if (next[idx]) next[idx] = fn(next[idx]);
  return next;
}

function applyEventToTurnList(
  prev: Turn[],
  idx: number,
  ev: ChatEvent,
  t: I18nStrings,
): Turn[] {
  return updateTurn(prev, idx, (turn) => {
    switch (ev.type) {
      case "conversation":
        return {
          ...turn,
          conversationId: typeof ev.data === "string" ? ev.data : extractId(ev.data, "conversation_id"),
        };
      case "planning":
        return appendStep(turn, "planning", t.chat.planning);
      case "plan": {
        const text = planText(ev.data);
        const noPlan = noPlanBody(text);
        if (noPlan !== null) {
          return appendStep(turn, "plan", t.chat.noPlan, { plan: [noPlan] });
        }
        return appendStep(
          turn,
          "plan",
          t.chat.planReady,
          { plan: planLinesWithBudget(text, planBudget(ev.data), t) },
        );
      }
      case "thinking":
        return appendStep(
          finishActiveThinking(turn),
          "thinking",
          thinkingLabel(ev.data, t),
          { startedAtMs: Date.now() },
        );
      case "tool_call": {
        const baseTurn = finishActiveThinking(turn);
        const d = (ev.data && typeof ev.data === "object")
          ? (ev.data as {
              name?: string;
              tool_call_id?: string;
              arguments?: Record<string, unknown>;
              display?: string;
              entry_names?: Record<string, string>;
              tag_names?: Record<string, string>;
            })
          : {};
        const args = d.arguments || {};
        const label = d.display
          ? `${t.chat.calling} ${d.display}`
          : formatToolCall(d.name || t.chat.tool, args, t);
        return appendStep(
          baseTurn, "tool_call", label,
          {
            args,
            toolName: d.name,
            toolCallId: d.tool_call_id,
            entryNames: d.entry_names,
            tagNames: d.tag_names,
          },
        );
      }
      case "tool_result": {
        const d = (ev.data && typeof ev.data === "object")
          ? (ev.data as {
              ok?: boolean;
              tool_call_id?: string;
              duration_ms?: number;
              error?: string;
              preview?: string;
            })
          : {};
        return markResult(
          turn,
          d.tool_call_id,
          d.ok === false ? "failed" : "ok",
          d.duration_ms,
          d.error,
          d.preview,
        );
      }
      case "user_artifact": {
        const artifact = parseUserArtifactEvent(ev.data);
        if (!artifact) return turn;
        return {
          ...turn,
          artifacts: [...(turn.artifacts ?? []), artifact],
        };
      }
      case "answer":
        return {
          ...finishActiveThinking(turn),
          answer: typeof ev.data === "string" ? ev.data : ev.raw,
        };
      case "done": {
        const d = (ev.data && typeof ev.data === "object")
          ? (ev.data as Turn["metrics"])
          : undefined;
        return { ...finishActiveThinking(turn), metrics: d, done: true };
      }
      case "error":
        return {
          ...finishActiveThinking(turn),
          error: typeof ev.data === "string" ? ev.data : ev.raw,
          done: true,
        };
      default:
        return turn;
    }
  });
}

function thinkingLabel(data: unknown, t: I18nStrings): string {
  if (!data || typeof data !== "object") return t.chat.thinking;
  const d = data as ThinkingEventData;
  const round = Number(d.round);
  const limit = Number(d.limit);
  if (!Number.isFinite(round) || round <= 0) return t.chat.thinking;
  if (!Number.isFinite(limit) || limit <= 0) {
    return `${t.chat.thinking} (${round})`;
  }
  if (d.budget_upgraded) {
    const tier = d.budget_tier ? budgetTierLabel(d.budget_tier, t) : "";
    return tier
      ? `${t.chat.thinking} (${round}/${limit}, ${t.chat.budgetUpgraded(tier)})`
      : `${t.chat.thinking} (${round}/${limit}, ${t.chat.budgetUpgradedShort})`;
  }
  return `${t.chat.thinking} (${round}/${limit})`;
}

function budgetTierLabel(tier: "quick" | "standard" | "deep", t: I18nStrings): string {
  switch (tier) {
    case "quick": return t.chat.quickMode;
    case "standard": return t.chat.standardMode;
    case "deep": return t.chat.deepMode;
  }
}

function noPlanBody(data: unknown): string | null {
  const text = typeof data === "string" ? data.trim() : "";
  if (!text.startsWith("NO_PLAN:")) return null;
  return text.slice("NO_PLAN:".length).trim();
}

function planText(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const text = (data as { text?: unknown }).text;
    if (typeof text === "string") return text;
  }
  return "";
}

function planBudget(data: unknown): PlanBudgetData | null {
  if (!data || typeof data !== "object") return null;
  const budget = (data as { budget?: unknown }).budget;
  return budget && typeof budget === "object" ? budget as PlanBudgetData : null;
}

function planLines(data: unknown): string[] {
  const text = typeof data === "string" ? data.trim() : "";
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

function planLinesWithBudget(
  text: string,
  budget: PlanBudgetData | null,
  t: I18nStrings,
): string[] {
  const lines = planLines(text);
  const budgetLine = budgetLabel(budget, t);
  return budgetLine ? [budgetLine, ...lines] : lines;
}

function budgetLabel(budget: PlanBudgetData | null, t: I18nStrings): string | null {
  if (!budget?.tier) return null;
  const limit = Number(budget.limit);
  const tier = budgetTierLabel(budget.tier, t);
  return Number.isFinite(limit) && limit > 0
    ? t.chat.budgetPicked(tier, limit)
    : t.chat.budgetPickedNoLimit(tier);
}

function formatToolCall(
  name: string,
  args: Record<string, unknown>,
  t: I18nStrings,
): string {
  const keys = Object.keys(args);
  if (keys.length === 0) return `${t.chat.calling} ${name}`;
  const parts: string[] = [];
  for (const k of keys) {
    const v = args[k];
    let s = typeof v === "string" ? v : JSON.stringify(v);
    if (s.length > 24) s = s.slice(0, 21) + "...";
    parts.push(`${k}=${s}`);
  }
  let inner = parts.join(", ");
  if (inner.length > 60) inner = inner.slice(0, 57) + "...";
  return `${t.chat.calling} ${name}(${inner})`;
}

function extractId(data: unknown, key: string): string | undefined {
  if (data && typeof data === "object" && key in data) {
    const v = (data as Record<string, unknown>)[key];
    return typeof v === "string" ? v : undefined;
  }
  return undefined;
}

function extractSessionNameFromPlan(data: unknown): string | null {
  const text = typeof data === "string" ? data : "";
  for (const line of text.split("\n").reverse()) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const prefix = "Session name:";
    if (!trimmed.toLowerCase().startsWith(prefix.toLowerCase())) return null;
    const name = trimmed.slice(prefix.length).trim().replace(/^["'`]+|["'`]+$/g, "");
    return name || null;
  }
  return null;
}

function appendStep(
  t: Turn,
  kind: Step["kind"],
  label: string,
  extra?: {
    args?: Record<string, unknown>;
    plan?: string[];
    toolName?: string;
    toolCallId?: string;
    entryNames?: Record<string, string>;
    tagNames?: Record<string, string>;
    startedAtMs?: number;
  },
): Turn {
  return {
    ...t,
    steps: [
      ...t.steps,
      {
        kind,
        label,
        args: extra?.args,
        plan: extra?.plan,
        toolName: extra?.toolName,
        toolCallId: extra?.toolCallId,
        entryNames: extra?.entryNames,
        tagNames: extra?.tagNames,
        result: undefined,
        startedAtMs: extra?.startedAtMs,
        durationMs: undefined,
      },
    ],
  };
}

function finishActiveThinking(t: Turn): Turn {
  let changed = false;
  const nowMs = Date.now();
  const steps = t.steps.map((step) => {
    if (step.kind !== "thinking" || step.startedAtMs == null || step.durationMs != null) {
      return step;
    }
    changed = true;
    return { ...step, durationMs: Math.max(0, nowMs - step.startedAtMs) };
  });
  return changed ? { ...t, steps } : t;
}

function markResult(
  t: Turn,
  toolCallId: string | undefined,
  result: "ok" | "failed",
  durationMs?: number,
  error?: string,
  resultPreview?: string,
): Turn {
  if (t.steps.length === 0) return t;
  const steps = [...t.steps];
  let target = -1;
  if (toolCallId) {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].kind === "tool_call" && steps[i].toolCallId === toolCallId) {
        target = i;
        break;
      }
    }
  }
  if (target === -1) {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].kind === "tool_call" && !steps[i].result) {
        target = i;
        break;
      }
    }
  }
  if (target === -1) return t;
  steps[target] = { ...steps[target], result, durationMs, error, resultPreview };
  return { ...t, steps };
}

function replayedToTurn(rt: ReplayedTurn, t: I18nStrings): Turn {
  const steps: Step[] = [];
  if (rt.plan_text) {
    const text = rt.plan_text.trim();
    const noPlan = noPlanBody(text);
    if (noPlan !== null) {
      steps.push({ kind: "plan", label: t.chat.noPlan, plan: [noPlan] });
    } else {
      steps.push({
        kind: "plan",
        label: t.chat.planReady,
        plan: planLines(text),
      });
    }
  }

  for (const tc of rt.tool_calls) {
    const name = tc.name || t.chat.tool;
    const label = tc.display
      ? `${t.chat.calling} ${tc.display}`
      : formatToolCall(name, tc.arguments || {}, t);
    steps.push({
      kind: "tool_call",
      label,
      args: tc.arguments,
      toolName: name,
      toolCallId: tc.tool_call_id ?? undefined,
      result: tc.ok ? "ok" : "failed",
      durationMs: tc.duration_ms ?? undefined,
      error: tc.error ?? undefined,
      resultPreview: tc.preview ?? undefined,
    });
  }

  const artifacts: UserArtifact[] = [];
  for (const raw of rt.artifacts ?? []) {
    const artifact = parseUserArtifact(raw);
    if (artifact) artifacts.push(artifact);
  }

  return {
    query: rt.user_message,
    conversationId: rt.conversation_id,
    steps,
    artifacts: artifacts.length > 0 ? artifacts : undefined,
    answer: rt.error ? null : rt.agent_response,
    metrics: rt.metrics,
    error: rt.error,
    done: rt.ended_at !== null || !!rt.error,
  };
}

function inferTranscriptMode(turns: ReplayedTurn[]): ChatMode {
  for (let i = turns.length - 1; i >= 0; i--) {
    const m = turns[i].mode;
    if (m === "quick" || m === "deep" || m === "auto") return m;
  }
  return "auto";
}
