from __future__ import annotations

import re

STOP_TOPICS = {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "did", "does", "doing", "done", "have", "having", "will", "would", "could",
    "should", "can", "may", "might", "must", "shall", "that", "this", "these",
    "those", "there", "their", "they", "them", "with", "from", "into", "about",
    "above", "below", "between", "under", "after", "before", "during", "while",
    "today", "yesterday", "tomorrow", "earlier", "later", "now", "then",
    "please", "tell", "give", "show", "find", "check", "explain", "compare",
    "latest", "current", "recent", "asked", "question", "answer", "know",
    "just", "very", "much", "more", "most", "some", "many", "such", "also",
    "your", "mine", "ours", "you", "the", "and", "for", "are", "was", "were",
}


def extract_topics(user_query: str, assistant_answer: str, max_topics: int = 8) -> list[str]:
    """Zero-cost deterministic entity/keyword extractor (<1ms, 0 LLM calls)."""
    seen: dict[str, int] = {}

    # Boost capitalized multi-word or proper phrases in query
    for phrase in re.findall(r"\b[A-Z][a-zA-Z0-9.+#\-]*(?:\s+[A-Z][a-zA-Z0-9.+#\-]*){0,2}\b", user_query):
        cleaned = phrase.strip()
        if len(cleaned) >= 2 and cleaned.lower() not in STOP_TOPICS:
            key = cleaned.lower()
            seen[cleaned] = max(seen.get(cleaned, 0), 4)
            _ = key

    # Extract meaningful tokens from query (weight 3) then answer (weight 1)
    for text, weight in ((user_query, 3), (assistant_answer[:800], 1)):
        for tok in re.findall(r"[A-Za-z0-9_+#.\-]{2,}", text):
            lower = tok.lower().strip(".-")
            if len(lower) < 2 or lower in STOP_TOPICS or lower.isdigit():
                continue
            # Deduplicate case-insensitively while keeping nicer casing
            existing_key = next((k for k in seen if k.lower() == lower), None)
            if existing_key:
                seen[existing_key] += weight
            else:
                seen[tok] = weight

    ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in ranked[:max_topics]]


def summarize_assistant_response(answer: str, max_chars: int = 320) -> str:
    """Create a compact factual summary of the assistant turn without extra LLM calls."""
    # Remove citation brackets and markdown formatting clutter for crisp memory storage
    cleaned = re.sub(r"\[(\d+)\]", "", answer)
    cleaned = re.sub(r"[#*_`>]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{clipped}..."
