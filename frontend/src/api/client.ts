import {
  AgentTrace,
  ChatMessage,
  ChatSession,
  Citation,
  ConfigResponse,
  MemoryTimelineItem,
  RuntimeProviderOverride,
} from "../types";

export function getClientTimezone(): { tz_name: string; tz_offset_minutes: number } {
  const tz_name = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const tz_offset_minutes = -new Date().getTimezoneOffset();
  return { tz_name, tz_offset_minutes };
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("Failed to load config");
  return res.json();
}

export async function fetchSessions(): Promise<ChatSession[]> {
  const res = await fetch("/api/sessions");
  if (!res.ok) throw new Error("Failed to load sessions");
  return res.json();
}

export async function createSession(title = "New Chat"): Promise<ChatSession> {
  const res = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete session");
}

export async function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!res.ok) throw new Error("Failed to load messages");
  return res.json();
}

export async function fetchMemories(query = ""): Promise<MemoryTimelineItem[]> {
  const { tz_name, tz_offset_minutes } = getClientTimezone();
  const params = new URLSearchParams({
    tz_name,
    tz_offset_minutes: String(tz_offset_minutes),
    limit: "120",
  });
  if (query.trim()) params.set("q", query.trim());
  const res = await fetch(`/api/memories?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to load memory timeline");
  return res.json();
}

export interface StreamHandlers {
  onSessionId?: (sessionId: string) => void;
  onPhase?: (phase: string, label: string) => void;
  onToken?: (text: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onDone?: (payload: {
    session_id: string;
    answer: string;
    citations: Citation[];
    trace: AgentTrace;
  }) => void;
  onError?: (message: string) => void;
}

export async function streamChat(
  params: {
    sessionId: string | null;
    message: string;
    override?: RuntimeProviderOverride | null;
  },
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const { tz_name, tz_offset_minutes } = getClientTimezone();
  const body: Record<string, unknown> = {
    session_id: params.sessionId,
    message: params.message,
    tz_name,
    tz_offset_minutes,
  };
  if (params.override?.provider) {
    body.provider = params.override.provider;
    if (params.override.model) body.model = params.override.model;
    if (params.override.apiKey) body.api_key = params.override.apiKey;
  }

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  const headerSessionId = res.headers.get("X-Session-Id");
  if (headerSessionId) handlers.onSessionId?.(headerSessionId);

  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}: Failed to start chat stream`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const processFrame = (rawFrame: string) => {
    const lines = rawFrame.split(/\r?\n/);
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (!dataLines.length) return;
    const payloadStr = dataLines.join("\n");
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(payloadStr);
    } catch {
      return;
    }

    if (eventName === "phase") {
      handlers.onPhase?.(String(data.phase || ""), String(data.label || ""));
    } else if (eventName === "token") {
      handlers.onToken?.(String(data.text || ""));
    } else if (eventName === "citations") {
      handlers.onCitations?.((data.citations as Citation[]) || []);
    } else if (eventName === "done") {
      handlers.onDone?.(
        data as {
          session_id: string;
          answer: string;
          citations: Citation[];
          trace: AgentTrace;
        }
      );
    } else if (eventName === "error") {
      handlers.onError?.(String(data.message || "Unknown agent error"));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex = buffer.indexOf("\n\n");
    while (sepIndex !== -1) {
      const frame = buffer.slice(0, sepIndex).trim();
      buffer = buffer.slice(sepIndex + 2);
      if (frame) processFrame(frame);
      sepIndex = buffer.indexOf("\n\n");
    }
  }

  if (buffer.trim()) {
    processFrame(buffer.trim());
  }
}
