from __future__ import annotations

from typing import Any

# Strictly ONE tool exposed to the LLM, honoring the core design constraint.
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the live web for up-to-date facts, news, documentation, prices, "
            "or verification. Returns ranked results with URLs, publish dates, and extracted page excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Concise, targeted search query. Include specific entities, versions, "
                        "or years when freshness matters."
                    ),
                },
                "freshness": {
                    "type": "string",
                    "enum": ["any", "day", "week", "month", "year"],
                    "description": "Time filter for recent events. Use 'day' or 'week' for breaking news.",
                },
                "deep_extract": {
                    "type": "boolean",
                    "description": "Extract full readable excerpts from top URLs for higher factual accuracy.",
                },
            },
            "required": ["query"],
        },
    },
}

AGENT_TOOLS: list[dict[str, Any]] = [WEB_SEARCH_TOOL]
