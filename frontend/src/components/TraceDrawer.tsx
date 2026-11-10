import { Activity, Clock, Cpu, Database, Search, ShieldCheck, X } from "lucide-react";
import { AgentTrace } from "../types";

interface TraceDrawerProps {
  trace: AgentTrace | null;
  onClose: () => void;
}

function TimingBar({ label, valueMs, maxMs }: { label: string; valueMs?: number; maxMs: number }) {
  const val = valueMs ?? 0;
  const pct = maxMs > 0 ? Math.min(100, Math.max(2, (val / maxMs) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span className="font-mono text-zinc-200">{val.toFixed(1)} ms</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
        <div className="h-full rounded-full bg-emerald-500/80 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function TraceDrawer({ trace, onClose }: TraceDrawerProps) {
  if (!trace) return null;

  const totalMs = trace.timings_ms.total_ms || 1;

  return (
    <aside className="w-full lg:w-[360px] shrink-0 border-l border-zinc-800 bg-zinc-950/95 flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-zinc-100">Live Agent Trace</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 text-zinc-400 hover:text-zinc-100 rounded hover:bg-zinc-800"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5 text-xs">
        {/* Strict 1-Tool Invariant Proof */}
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-emerald-300">
              Single-Tool Invariant: {trace.tool_schema_count} tool exposed
            </p>
            <p className="text-zinc-300/90 mt-0.5">
              Only <code className="px-1 py-0.5 rounded bg-zinc-900 text-emerald-300">web_search</code> is registered in the LLM schema. Memory &amp; routing run in the orchestrator.
            </p>
          </div>
        </div>

        {/* Route & Model */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-zinc-400 font-medium uppercase tracking-wider text-[11px]">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span>Routing &amp; Inference</span>
          </div>
          <div className="grid grid-cols-2 gap-y-1.5 gap-x-2">
            <span className="text-zinc-400">Route Mode</span>
            <span className="font-mono text-cyan-300 text-right">{trace.route_mode}</span>
            <span className="text-zinc-400">Route Reason</span>
            <span className="font-mono text-zinc-200 text-right truncate" title={trace.route_reason}>
              {trace.route_reason}
            </span>
            <span className="text-zinc-400">LLM Provider</span>
            <span className="font-mono text-zinc-200 text-right">
              {trace.provider} ({trace.model})
            </span>
            <span className="text-zinc-400">Grounding</span>
            <span className="text-emerald-300 font-medium text-right">{trace.grounding_badge}</span>
          </div>
        </div>

        {/* Latency Breakdown */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-zinc-400 font-medium uppercase tracking-wider text-[11px]">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              <span>Latency Breakdown</span>
            </div>
            <span className="font-mono text-emerald-300 font-semibold">
              {totalMs.toFixed(0)} ms
            </span>
          </div>
          <TimingBar label="Memory Recall" valueMs={trace.timings_ms.memory_recall_ms} maxMs={totalMs} />
          <TimingBar label="Query Router" valueMs={trace.timings_ms.routing_ms} maxMs={totalMs} />
          <TimingBar label="Web Search" valueMs={trace.timings_ms.search_ms} maxMs={totalMs} />
          <TimingBar label="Time to First Token (TTFT)" valueMs={trace.timings_ms.ttft_ms} maxMs={totalMs} />
        </div>

        {/* Web Search Tool Calls */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-zinc-400 font-medium uppercase tracking-wider text-[11px]">
            <Search className="w-3.5 h-3.5 text-emerald-400" />
            <span>web_search Calls ({trace.tool_calls.length})</span>
          </div>
          {trace.tool_calls.length === 0 ? (
            <p className="text-zinc-500 italic rounded-lg border border-zinc-800/70 bg-zinc-900/40 p-2.5">
              Fast-path bypass — 0 web searches executed.
            </p>
          ) : (
            <div className="space-y-2">
              {trace.tool_calls.map((tc, idx) => (
                <div
                  key={`${tc.query}-${idx}`}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5 space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-zinc-100 truncate">“{tc.query}”</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                        tc.cache_hit
                          ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                          : "bg-zinc-800 text-zinc-300"
                      }`}
                    >
                      {tc.cache_hit ? "CACHE HIT" : tc.provider}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-zinc-400">
                    <span>
                      {tc.results_count} results • freshness: {tc.freshness}
                    </span>
                    <span className="font-mono text-zinc-300">{tc.elapsed_ms.toFixed(0)} ms</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recalled Temporal Memories */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-zinc-400 font-medium uppercase tracking-wider text-[11px]">
            <Database className="w-3.5 h-3.5 text-violet-400" />
            <span>Memories Injected ({trace.memories_recalled.length})</span>
          </div>
          {trace.memories_recalled.length === 0 ? (
            <p className="text-zinc-500 italic rounded-lg border border-zinc-800/70 bg-zinc-900/40 p-2.5">
              No prior memories matched this query.
            </p>
          ) : (
            <div className="space-y-2">
              {trace.memories_recalled.map((m) => (
                <div
                  key={m.id}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-2.5 space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px] text-violet-300 font-mono">
                    <span>{m.formatted_time}</span>
                    <span>RRF {m.score.toFixed(3)}</span>
                  </div>
                  <p className="text-zinc-200 line-clamp-2">“{m.user_query}”</p>
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {m.reasons.map((r) => (
                      <span
                        key={r}
                        className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]"
                      >
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
