import { useEffect, useState } from "react";
import { CalendarClock, Search, Tag } from "lucide-react";
import { fetchMemories } from "../api/client";
import { MemoryTimelineItem } from "../types";

interface MemoryTimelineProps {
  refreshSignal: number;
  onSelectSession: (sessionId: string) => void;
}

export function MemoryTimeline({ refreshSignal, onSelectSession }: MemoryTimelineProps) {
  const [items, setItems] = useState<MemoryTimelineItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const rows = await fetchMemories(query);
        if (active) setItems(rows);
      } catch {
        // Ignore transient fetch errors
      } finally {
        if (active) setLoading(false);
      }
    };
    const timer = setTimeout(load, query ? 180 : 0);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query, refreshSignal]);

  // Group chronologically by local_date
  const grouped = items.reduce<Record<string, MemoryTimelineItem[]>>((acc, item) => {
    const key = item.local_date || "Recent";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});

  return (
    <div className="flex flex-col h-full">
      <div className="p-2.5 border-b border-zinc-800">
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-2.5 top-2.5" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter what you asked..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-emerald-500/60"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-4">
        {loading && items.length === 0 ? (
          <p className="text-xs text-zinc-500 text-center py-6">Loading temporal memories...</p>
        ) : items.length === 0 ? (
          <div className="text-center py-8 px-3">
            <CalendarClock className="w-7 h-7 text-zinc-600 mx-auto mb-2" />
            <p className="text-xs text-zinc-400">No memories recorded yet.</p>
            <p className="text-[11px] text-zinc-500 mt-1">
              Every prompt is indexed with exact timestamps across sessions.
            </p>
          </div>
        ) : (
          Object.entries(grouped).map(([dateStr, group]) => (
            <div key={dateStr} className="space-y-1.5">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 px-1">
                {dateStr}
              </div>
              {group.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectSession(item.session_id)}
                  className="w-full text-left rounded-lg border border-zinc-800/80 bg-zinc-900/50 hover:bg-zinc-900 hover:border-zinc-700 p-2.5 transition-colors space-y-1.5"
                >
                  <div className="text-[10px] font-mono text-emerald-400/90">
                    {item.formatted_time}
                  </div>
                  <p className="text-xs font-medium text-zinc-200 line-clamp-2">
                    {item.user_query}
                  </p>
                  {item.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {item.topics.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-[10px]"
                        >
                          <Tag className="w-2.5 h-2.5" />
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
