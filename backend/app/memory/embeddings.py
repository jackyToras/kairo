from __future__ import annotations

import hashlib
import math
import re
import time

import httpx


def hash_embed(text: str, dim: int = 256) -> list[float]:
    """Deterministic, zero-dependency char/word n-gram signed hash embedding."""
    vec = [0.0] * dim
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    if not normalized:
        return vec

    words = re.findall(r"[a-z0-9_+#.\-]+", normalized)
    features: list[tuple[str, float]] = []

    for w in words:
        features.append((f"w:{w}", 1.5))
        if len(w) >= 4:
            for i in range(len(w) - 2):
                features.append((f"c:{w[i:i+3]}", 0.45))

    for i in range(len(words) - 1):
        features.append((f"b:{words[i]}_{words[i+1]}", 1.8))

    for feat, weight in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        inv = 1.0 / norm
        vec = [round(v * inv, 6) for v in vec]
    return vec


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    if dot <= 0:
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class HybridEmbedder:
    """Uses free local Ollama embeddings when healthy, falling back to hash_embed."""

    def __init__(self, ollama_base_url: str, embed_model: str) -> None:
        # ollama_base_url may end in /v1; native embed API lives at root /api/embed
        self.base_root = ollama_base_url.rstrip("/")
        if self.base_root.endswith("/v1"):
            self.base_root = self.base_root[:-3]
        self.embed_model = embed_model
        self._ollama_ok: bool | None = None
        self._last_check_ts: float = 0.0

    async def embed(self, text: str, allow_remote: bool = True) -> tuple[str, list[float]]:
        now = time.time()
        if allow_remote and self.embed_model:
            if self._ollama_ok is False and (now - self._last_check_ts) < 60.0:
                return "hash-v1", hash_embed(text)

            try:
                async with httpx.AsyncClient(timeout=1.5) as client:
                    resp = await client.post(
                        f"{self.base_root}/api/embed",
                        json={"model": self.embed_model, "input": text[:2000]},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        embeddings = data.get("embeddings") or []
                        if embeddings and isinstance(embeddings[0], list):
                            self._ollama_ok = True
                            self._last_check_ts = now
                            return f"ollama:{self.embed_model}", [float(x) for x in embeddings[0]]
            except Exception:
                self._ollama_ok = False
                self._last_check_ts = now

        return "hash-v1", hash_embed(text)
