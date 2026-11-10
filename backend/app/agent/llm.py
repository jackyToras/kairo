from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import ResolvedLLMConfig


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMStreamEvent:
    kind: str  # "token" | "tool_calls" | "done" | "error"
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    raw_content: str = ""


def _parse_json_tool_fallback(text: str) -> list[ToolCallRequest] | None:
    """Detects raw JSON tool calls emitted in content by smaller open-weight models."""
    stripped = text.strip()
    if not stripped:
        return None

    # Strip markdown code fences or <tool_call> wrappers
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I | re.S).strip()
    cleaned = re.sub(r"</?tool_call>", "", cleaned, flags=re.I).strip()

    if not (cleaned.startswith("{") or cleaned.startswith("[")):
        return None

    try:
        parsed = json.loads(cleaned)
    except Exception:
        return None

    items = parsed if isinstance(parsed, list) else [parsed]
    calls: list[ToolCallRequest] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or (item.get("function") or {}).get("name")
        args = item.get("arguments") or item.get("parameters") or (item.get("function") or {}).get("arguments")
        if name == "web_search":
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"query": args}
            if isinstance(args, dict) and args.get("query"):
                calls.append(ToolCallRequest(id=f"call_fallback_{idx}", name="web_search", arguments=args))
    return calls or None


class LLMClient:
    """Unified async streaming OpenAI-compatible client for free-tier & local LLMs."""

    def __init__(self, timeout_seconds: float = 45.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def stream_chat(
        self,
        config: ResolvedLLMConfig,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        tool_choice: str = "auto",
    ) -> AsyncIterator[LLMStreamEvent]:
        if not config.is_local and not config.api_key:
            yield LLMStreamEvent(
                kind="error",
                text=(
                    f"No API key configured for provider '{config.provider}'. "
                    "Set it in .env or switch to local Ollama (free, zero-key) in Settings."
                ),
            )
            return

        url = f"{config.base_url.rstrip('/')}/chat/completions"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            **config.extra_headers,
        }
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        choices_to_try = [tool_choice, "auto"] if (tools and tool_choice == "required") else [tool_choice]
        timeout = httpx.Timeout(self.timeout_seconds, connect=8.0)
        accumulated_text = ""
        tool_buffers: dict[int, dict[str, str]] = {}

        # Small lookahead buffer only when tools are enabled to catch raw JSON tool output
        lookahead_buf = ""
        lookahead_decided = not bool(tools)

        try:
            for active_choice in choices_to_try:
                if tools:
                    payload["tool_choice"] = active_choice
                async with (
                    httpx.AsyncClient(timeout=timeout) as client,
                    client.stream("POST", url, headers=headers, json=payload) as resp,
                ):
                    if resp.status_code == 400 and active_choice == "required" and len(choices_to_try) > 1:
                        continue
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")
                        yield LLMStreamEvent(
                            kind="error",
                            text=f"LLM provider '{config.provider}' returned HTTP {resp.status_code}: {body[:350]}",
                        )
                        return

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        # Handle tool call deltas
                        for tc in delta.get("tool_calls") or []:
                            idx = int(tc.get("index", 0))
                            buf = tool_buffers.setdefault(
                                idx,
                                {"id": tc.get("id") or f"call_{idx}", "name": "", "arguments": ""},
                            )
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                buf["name"] += fn["name"]
                            if fn.get("arguments"):
                                buf["arguments"] += fn["arguments"]

                        # Handle content tokens
                        token = delta.get("content")
                        if token:
                            accumulated_text += token
                            if not lookahead_decided:
                                lookahead_buf += token
                                stripped_la = lookahead_buf.lstrip()
                                if len(stripped_la) >= 12 or ("\n" in lookahead_buf and len(stripped_la) > 0):
                                    # Check if the model is emitting a JSON tool call as text
                                    if stripped_la.startswith(("{", "[", "<tool_call", "```json")):
                                        # Keep buffering to parse at stream end
                                        if len(stripped_la) > 400:
                                            # Clearly prose/markdown JSON, flush and stop buffering
                                            lookahead_decided = True
                                            yield LLMStreamEvent(kind="token", text=lookahead_buf)
                                            lookahead_buf = ""
                                    else:
                                        lookahead_decided = True
                                        yield LLMStreamEvent(kind="token", text=lookahead_buf)
                                        lookahead_buf = ""
                            else:
                                yield LLMStreamEvent(kind="token", text=token)
                    break

        except httpx.ConnectError:
            hint = (
                "Make sure Ollama is running (`ollama serve`) or select a free cloud tier (Groq/Gemini) in Settings."
                if config.is_local
                else f"Could not reach {config.base_url}."
            )
            yield LLMStreamEvent(kind="error", text=f"Connection failed to {config.provider}. {hint}")
            return
        except Exception as exc:
            yield LLMStreamEvent(kind="error", text=f"Streaming error from {config.provider}: {exc}")
            return

        # Assemble native tool calls if present
        if tool_buffers:
            parsed_calls: list[ToolCallRequest] = []
            for idx in sorted(tool_buffers):
                buf = tool_buffers[idx]
                raw_args = buf["arguments"].strip()
                try:
                    args_dict = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args_dict = {"query": raw_args}
                parsed_calls.append(
                    ToolCallRequest(
                        id=buf["id"],
                        name=buf["name"] or "web_search",
                        arguments=args_dict,
                    )
                )
            yield LLMStreamEvent(kind="tool_calls", tool_calls=parsed_calls, raw_content=accumulated_text)
            return

        # Check lookahead buffer for fallback JSON tool call
        if lookahead_buf:
            fallback_calls = _parse_json_tool_fallback(accumulated_text)
            if fallback_calls:
                yield LLMStreamEvent(kind="tool_calls", tool_calls=fallback_calls, raw_content=accumulated_text)
                return
            yield LLMStreamEvent(kind="token", text=lookahead_buf)

        yield LLMStreamEvent(kind="done", raw_content=accumulated_text)
