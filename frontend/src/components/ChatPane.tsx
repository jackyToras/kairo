import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  ArrowUp,
  Bot,
  Clock,
  Loader2,
  Search,
  Sparkles,
  Square,
  User,
} from "lucide-react";
import { AgentTrace, ChatMessage } from "../types";
import { CitationList } from "./CitationList";

interface ChatPaneProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onInspectTrace: (trace: AgentTrace) => void;
}

const DEMO_PROMPTS = [
  {
    label: "Live Web Grounding",
    prompt: "What is the latest FastAPI release version and key features?",
    tag: "web_search",
  },
  {
    label: "Multi-Source Comparison",
    prompt: "Compare Groq vs Google Gemini free tier limits in 2026",
    tag: "web_search",
  },
  {
    label: "Temporal Memory (What & When)",
    prompt: "What did I ask you earlier today and when?",
    tag: "0ms search",
  },
  {
    label: "Cross-Session Recall",
    prompt: "When did I first ask about FastAPI?",
    tag: "memory",
  },
];

function linkifyCitations(markdown: string): string {
  // Replace [1] outside code blocks with markdown links #cit-1
  const parts = markdown.split(/(```[\s\S]*?```|`[^`]+`)/g);
  return parts
    .map((part, idx) => {
      if (idx % 2 === 1) return part;
      return part.replace(/\[(\d+)\](?!\()/g, "[[$1]](#cit-$1)");
    })
    .join("");
}

function formatMessageTime(iso: string): string {
  try {
    const dt = new Date(iso);
    return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function ChatPane({
  messages,
  isStreaming,
  onSend,
  onStop,
  onInspectTrace,
}: ChatPaneProps) {
  const [input, setInput] = useState("");
  const [highlightedCitation, setHighlightedCitation] = useState<{
    msgId: string;
    citId: number;
  } | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    onSend(trimmed);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-zinc-950">
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
        {messages.length === 0 ? (
          <div className="max-w-2xl mx-auto h-full flex flex-col justify-center py-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-medium w-fit mb-4">
              <Sparkles className="w-3.5 h-3.5" />
              <span>1 Tool (web_search) • Fast Routing • Temporal Memory</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-zinc-100">
              Ask anything. Verify everything. Remember when.
            </h1>
            <p className="text-sm text-zinc-400 mt-2 leading-relaxed">
              Kairo pairs a strict single-tool <code className="text-emerald-300">web_search</code> loop with
              SQLite FTS5 + semantic temporal memory—so you get fast direct answers, verified citations, and exact
              recall of what you asked across sessions.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-7">
              {DEMO_PROMPTS.map((item) => (
                <button
                  key={item.prompt}
                  type="button"
                  onClick={() => onSend(item.prompt)}
                  className="text-left rounded-xl border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900 hover:border-emerald-500/50 p-3.5 transition-all group"
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs font-semibold text-zinc-200 group-hover:text-emerald-300">
                      {item.label}
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                      {item.tag}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 line-clamp-2">{item.prompt}</p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot className="w-4 h-4 text-emerald-400" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-zinc-800/90 text-zinc-100 border border-zinc-700/70"
                      : "bg-zinc-900/60 text-zinc-100 border border-zinc-800/90 flex-1"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-1.5 border-b border-zinc-800/70">
                      <div className="flex items-center gap-2 text-[11px]">
                        {msg.isStreaming && msg.phaseLabel ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-300 font-medium">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            {msg.phaseLabel}
                          </span>
                        ) : msg.trace ? (
                          <>
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-medium">
                              {msg.trace.tool_calls.length > 0 && <Search className="w-3 h-3" />}
                              {msg.trace.grounding_badge}
                            </span>
                            {msg.trace.timings_ms.total_ms !== undefined && (
                              <span className="inline-flex items-center gap-1 text-zinc-400 font-mono">
                                <Clock className="w-3 h-3" />
                                {msg.trace.timings_ms.total_ms.toFixed(0)} ms
                              </span>
                            )}
                          </>
                        ) : (
                          <span className="text-zinc-500">Kairo</span>
                        )}
                      </div>

                      {msg.trace && (
                        <button
                          type="button"
                          onClick={() => onInspectTrace(msg.trace!)}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] text-zinc-400 hover:text-emerald-300 hover:bg-zinc-800 transition-colors"
                        >
                          <Activity className="w-3 h-3" />
                          Trace
                        </button>
                      )}
                    </div>
                  )}

                  {msg.role === "user" ? (
                    <div>
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      <p className="text-[10px] text-zinc-400 mt-1 text-right font-mono">
                        {formatMessageTime(msg.created_at)}
                      </p>
                    </div>
                  ) : (
                    <>
                      <div className="prose-kairo text-sm text-zinc-200">
                        {msg.content ? (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ href, children }) => {
                                if (href?.startsWith("#cit-")) {
                                  const cid = Number(href.replace("#cit-", ""));
                                  return (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setHighlightedCitation({ msgId: msg.id, citId: cid })
                                      }
                                      className="inline-flex items-center justify-center px-1.5 py-0 mx-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[11px] font-semibold hover:bg-emerald-500/30 align-baseline"
                                    >
                                      {children}
                                    </button>
                                  );
                                }
                                return (
                                  <a href={href} target="_blank" rel="noopener noreferrer">
                                    {children}
                                  </a>
                                );
                              },
                            }}
                          >
                            {linkifyCitations(msg.content)}
                          </ReactMarkdown>
                        ) : (
                          msg.isStreaming && (
                            <span className="text-zinc-500 text-xs italic">Preparing response...</span>
                          )
                        )}
                      </div>
                      <CitationList
                        citations={msg.citations}
                        highlightedId={
                          highlightedCitation?.msgId === msg.id ? highlightedCitation.citId : null
                        }
                      />
                    </>
                  )}
                </div>

                {msg.role === "user" && (
                  <div className="w-7 h-7 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-zinc-300" />
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-zinc-800/90 bg-zinc-950/90 px-4 sm:px-8 py-4">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto flex items-end gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/70 px-3.5 py-2.5 focus-within:border-emerald-500/60 transition-colors"
        >
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a live question or ask what you queried yesterday..."
            className="flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 resize-none focus:outline-none max-h-36 py-1"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="p-2 rounded-xl bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40 shrink-0"
              title="Stop streaming"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="p-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:bg-zinc-800 disabled:text-zinc-500 text-zinc-950 transition-colors shrink-0"
              title="Send message"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
