import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bot,
  CalendarClock,
  MessageSquarePlus,
  MessagesSquare,
  PanelLeft,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import {
  deleteSession,
  fetchConfig,
  fetchMessages,
  fetchSessions,
  streamChat,
} from "./api/client";
import { ChatPane } from "./components/ChatPane";
import { MemoryTimeline } from "./components/MemoryTimeline";
import { ProviderModal } from "./components/ProviderModal";
import { TraceDrawer } from "./components/TraceDrawer";
import {
  AgentTrace,
  ChatMessage,
  ChatSession,
  ConfigResponse,
  RuntimeProviderOverride,
} from "./types";

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sidebarTab, setSidebarTab] = useState<"chats" | "memories">("chats");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [providerOverride, setProviderOverride] = useState<RuntimeProviderOverride | null>(null);
  const [providerModalOpen, setProviderModalOpen] = useState(false);

  const [activeTrace, setActiveTrace] = useState<AgentTrace | null>(null);
  const [traceDrawerOpen, setTraceDrawerOpen] = useState(false);

  const [isStreaming, setIsStreaming] = useState(false);
  const [memoryRefreshSignal, setMemoryRefreshSignal] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await fetchSessions();
      setSessions(list);
    } catch {
      // ignore initial load error
    }
  }, []);

  useEffect(() => {
    refreshSessions();
    fetchConfig().then(setConfig).catch(() => {});
  }, [refreshSessions]);

  const loadSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    try {
      const rows = await fetchMessages(sessionId);
      setMessages(rows);
      const lastWithTrace = [...rows].reverse().find((m) => m.trace && Object.keys(m.trace).length > 0);
      if (lastWithTrace?.trace) {
        setActiveTrace(lastWithTrace.trace);
      }
    } catch {
      setMessages([]);
    }
  };

  const handleNewChat = () => {
    if (isStreaming) return;
    setActiveSessionId(null);
    setMessages([]);
    setActiveTrace(null);
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    await deleteSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
      setMessages([]);
    }
    refreshSessions();
    setMemoryRefreshSignal((n) => n + 1);
  };

  const handleSend = async (text: string) => {
    const nowIso = new Date().toISOString();
    const userMsgId = `u-${Date.now()}`;
    const asstMsgId = `a-${Date.now()}`;

    const userMsg: ChatMessage = {
      id: userMsgId,
      session_id: activeSessionId || "pending",
      role: "user",
      content: text,
      created_at: nowIso,
      citations: [],
    };
    const asstMsg: ChatMessage = {
      id: asstMsgId,
      session_id: activeSessionId || "pending",
      role: "assistant",
      content: "",
      created_at: nowIso,
      citations: [],
      isStreaming: true,
      phaseLabel: "Starting...",
    };

    setMessages((prev) => [...prev, userMsg, asstMsg]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        {
          sessionId: activeSessionId,
          message: text,
          override: providerOverride,
        },
        {
          onSessionId: (sid) => {
            setActiveSessionId(sid);
          },
          onPhase: (_phase, label) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === asstMsgId ? { ...m, phaseLabel: label } : m))
            );
          },
          onToken: (tok) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstMsgId ? { ...m, content: m.content + tok } : m
              )
            );
          },
          onCitations: (citations) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === asstMsgId ? { ...m, citations } : m))
            );
          },
          onDone: (payload) => {
            setActiveSessionId(payload.session_id);
            setActiveTrace(payload.trace);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstMsgId
                  ? {
                      ...m,
                      session_id: payload.session_id,
                      content: payload.answer || m.content,
                      citations: payload.citations,
                      trace: payload.trace,
                      isStreaming: false,
                      phaseLabel: undefined,
                    }
                  : m
              )
            );
            refreshSessions();
            setTimeout(() => setMemoryRefreshSignal((n) => n + 1), 350);
          },
          onError: (errMsg) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstMsgId
                  ? {
                      ...m,
                      content: `⚠️ ${errMsg}`,
                      isStreaming: false,
                      phaseLabel: undefined,
                    }
                  : m
              )
            );
          },
        },
        controller.signal
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === asstMsgId
              ? {
                  ...m,
                  content: `⚠️ ${(err as Error).message}`,
                  isStreaming: false,
                  phaseLabel: undefined,
                }
              : m
          )
        );
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false, phaseLabel: undefined } : m))
    );
  };

  const displayedProvider = providerOverride?.provider || config?.active_provider || "ollama";
  const displayedModel = providerOverride?.model || config?.active_model || "mistral:latest";

  return (
    <div className="h-screen w-screen flex flex-col bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Top Bar */}
      <header className="h-12 shrink-0 border-b border-zinc-800 px-3 sm:px-4 flex items-center justify-between bg-zinc-950">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
            title="Toggle sidebar"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
              <Bot className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <span className="font-semibold text-sm tracking-tight">Kairo</span>
            <span className="hidden sm:inline-flex px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-emerald-300">
              1-Tool: web_search
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setProviderModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-zinc-800 bg-zinc-900/70 hover:border-zinc-700 text-xs text-zinc-300"
          >
            <SlidersHorizontal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="font-mono text-[11px] truncate max-w-[170px]">
              {displayedProvider} · {displayedModel}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setTraceDrawerOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-colors ${
              traceDrawerOpen
                ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-300"
                : "border-zinc-800 bg-zinc-900/70 text-zinc-300 hover:border-zinc-700"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Trace</span>
          </button>
        </div>
      </header>

      {/* Main 3-Pane Body */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {sidebarOpen && (
          <aside className="w-68 shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col h-full">
            <div className="p-2.5 space-y-2 border-b border-zinc-800">
              <button
                type="button"
                onClick={handleNewChat}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold text-xs transition-colors"
              >
                <MessageSquarePlus className="w-4 h-4" />
                New Chat
              </button>

              <div className="grid grid-cols-2 gap-1 p-0.5 rounded-lg bg-zinc-900 border border-zinc-800">
                <button
                  type="button"
                  onClick={() => setSidebarTab("chats")}
                  className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    sidebarTab === "chats"
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <MessagesSquare className="w-3.5 h-3.5" />
                  Chats
                </button>
                <button
                  type="button"
                  onClick={() => setSidebarTab("memories")}
                  className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    sidebarTab === "memories"
                      ? "bg-zinc-800 text-emerald-300"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <CalendarClock className="w-3.5 h-3.5" />
                  Memory
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden">
              {sidebarTab === "chats" ? (
                <div className="h-full overflow-y-auto p-2 space-y-1">
                  {sessions.length === 0 ? (
                    <p className="text-xs text-zinc-500 text-center py-6">
                      No chats yet. Start asking!
                    </p>
                  ) : (
                    sessions.map((s) => (
                      <div
                        key={s.id}
                        onClick={() => loadSession(s.id)}
                        className={`group flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg cursor-pointer text-xs transition-colors ${
                          activeSessionId === s.id
                            ? "bg-zinc-800/90 text-zinc-100"
                            : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                        }`}
                      >
                        <span className="truncate flex-1">{s.title}</span>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSession(e, s.id)}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-rose-300"
                          title="Delete chat"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <MemoryTimeline
                  refreshSignal={memoryRefreshSignal}
                  onSelectSession={(sid) => {
                    loadSession(sid);
                  }}
                />
              )}
            </div>

            <div className="px-3 py-2 border-t border-zinc-800 text-[11px] text-zinc-500 flex items-center justify-between">
              <span>Search: {config?.search_provider || "duckduckgo"}</span>
              <span className="text-emerald-400 font-mono">$0 Free</span>
            </div>
          </aside>
        )}

        <ChatPane
          messages={messages}
          isStreaming={isStreaming}
          onSend={handleSend}
          onStop={handleStop}
          onInspectTrace={(trace) => {
            setActiveTrace(trace);
            setTraceDrawerOpen(true);
          }}
        />

        {traceDrawerOpen && (
          <TraceDrawer trace={activeTrace} onClose={() => setTraceDrawerOpen(false)} />
        )}
      </div>

      {providerModalOpen && (
        <ProviderModal
          open={providerModalOpen}
          config={config}
          currentOverride={providerOverride}
          onSave={setProviderOverride}
          onClose={() => setProviderModalOpen(false)}
        />
      )}
    </div>
  );
}
