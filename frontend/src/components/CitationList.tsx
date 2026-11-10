import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Globe } from "lucide-react";
import { Citation } from "../types";

interface CitationListProps {
  citations: Citation[];
  highlightedId?: number | null;
}

export function CitationList({ citations, highlightedId }: CitationListProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (!citations.length) return null;

  return (
    <div className="mt-3 pt-2.5 border-t border-zinc-800/80">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-400 mb-2">
        <Globe className="w-3.5 h-3.5 text-emerald-400" />
        <span>Sources ({citations.length})</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {citations.map((cit) => {
          const isHighlighted = highlightedId === cit.id;
          const isExpanded = expandedId === cit.id || isHighlighted;
          const bodyPreview = cit.excerpt || cit.snippet;

          return (
            <div
              key={`${cit.id}-${cit.url}`}
              className={`rounded-lg border p-2.5 transition-colors bg-zinc-900/70 ${
                isHighlighted
                  ? "border-emerald-500/70 bg-emerald-950/20"
                  : "border-zinc-800 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <a
                  href={cit.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-2 min-w-0 group flex-1"
                >
                  <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded bg-emerald-500/15 text-emerald-300 text-[11px] font-semibold border border-emerald-500/30">
                    {cit.id}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-zinc-200 group-hover:text-emerald-300 truncate">
                      {cit.title}
                    </p>
                    <p className="text-[11px] text-zinc-400 flex items-center gap-1.5 mt-0.5 truncate">
                      <span>{cit.domain}</span>
                      {cit.published_date && (
                        <>
                          <span>•</span>
                          <span>{cit.published_date.slice(0, 10)}</span>
                        </>
                      )}
                    </p>
                  </div>
                </a>
                <div className="flex items-center gap-1 shrink-0">
                  {bodyPreview && (
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : cit.id)}
                      className="p-1 text-zinc-400 hover:text-zinc-200 rounded hover:bg-zinc-800"
                      title={isExpanded ? "Hide excerpt" : "Preview extracted excerpt"}
                    >
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                  )}
                  <a
                    href={cit.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-zinc-400 hover:text-emerald-300 rounded hover:bg-zinc-800"
                    title="Open source"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </div>

              {isExpanded && bodyPreview && (
                <p className="mt-2 text-[11px] leading-relaxed text-zinc-400 border-t border-zinc-800/80 pt-1.5 line-clamp-4">
                  {bodyPreview}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
