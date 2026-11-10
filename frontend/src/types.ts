export interface Citation {
  id: number;
  title: string;
  url: string;
  domain: string;
  snippet: string;
  excerpt?: string | null;
  published_date?: string | null;
  trust_score?: number;
}

export interface MemoryMatch {
  id: string;
  user_query: string;
  formatted_time: string;
  score: number;
  reasons: string[];
}

export interface ToolCallTrace {
  tool: string;
  query: string;
  freshness: string;
  provider: string;
  cache_hit: boolean;
  elapsed_ms: number;
  results_count: number;
}

export interface AgentTrace {
  route_mode: string;
  route_reason: string;
  provider: string;
  model: string;
  search_provider?: string | null;
  timings_ms: {
    memory_recall_ms?: number;
    routing_ms?: number;
    search_ms?: number;
    ttft_ms?: number;
    total_ms?: number;
  };
  memories_recalled: MemoryMatch[];
  tool_calls: ToolCallTrace[];
  tool_schema_count: number;
  grounding_badge: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  citations: Citation[];
  trace?: AgentTrace | null;
  isStreaming?: boolean;
  phaseLabel?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MemoryTimelineItem {
  id: string;
  session_id: string;
  user_query: string;
  assistant_summary: string;
  topics: string[];
  created_at: string;
  created_ts: number;
  local_date: string;
  formatted_time: string;
}

export interface ProviderPreset {
  id: string;
  label: string;
  default_model: string;
  requires_key: boolean;
  cost: string;
  notes: string;
}

export interface ConfigResponse {
  active_provider: string;
  active_model: string;
  is_free_tier: boolean;
  is_local: boolean;
  search_provider: string;
  configured_keys: Record<string, boolean>;
  presets: ProviderPreset[];
}

export interface RuntimeProviderOverride {
  provider: string;
  model: string;
  apiKey: string;
}
