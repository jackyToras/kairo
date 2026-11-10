# Kairo — Fast, Grounded Single-Tool Chat Agent

**Kairo** is a fast, source-grounded AI chat agent built with **strictly one tool (`web_search`)** and persistent **hybrid temporal-semantic memory**—designed to answer quickly, verify claims against live web pages, and accurately remember **what you asked and when** across sessions.

> **Architecture Deep Dive:** See [`DESIGN.md`](./DESIGN.md) for system diagrams, SQLite FTS5 + RRF schema, latency budgets, prompt-injection defenses, and tradeoff analysis.

---

## Key Capabilities

- **Strictly One Tool (`web_search`)**: The LLM tool schema registers only `web_search` (`backend/app/agent/tools.py`). Memory recall, temporal parsing, and routing run deterministically in the orchestrator so there is zero tool bloat and zero extra search-tool round-trips.
- **Fast Path + Streaming SSE**:
  - Sub-millisecond deterministic query router (`direct`, `memory_recall`, `web_search`, `hybrid_memory_web`).
  - Concurrent pre-turn memory recall + session history loading.
  - Real-time Server-Sent Events (`phase`, `route`, `token`, `citations`, `done`) + non-blocking background memory indexing (`0 ms` added to user wait time).
  - SQLite TTL search cache (`~9.5 ms` on cache hit).
- **Accurate & Source-Grounded**:
  - `web_search` runs **zero-key DuckDuckGo** (with optional Tavily/Brave) + **concurrent top-3 page extraction** (real `<article>` excerpts and `<meta>` publish dates, not just 150-char search snippets).
  - Domain trust + recency ranking, clickable inline `[1]` `[2]` citations, prompt-injection delimiter sanitization, and a **force-search guardrail** preventing small models from guessing on live/factual queries.
- **Remembers What You Asked & When**:
  - Persistent SQLite (`WAL` mode) + **FTS5 BM25** + **vector cosine similarity** fused with **Reciprocal Rank Fusion (RRF)**.
  - Temporal query planner resolves *"today"*, *"yesterday afternoon"*, *"3 days ago"*, *"on Nov 8"*, *"2026-11-05"*, *"first time"*, and *"most recent"* in your local timezone.
- **100% Free-Cost ($0) Options**:
  - Works out-of-the-box with **local Ollama** (`mistral:latest`, `nomic-embed-text`) + **zero-key DuckDuckGo**.
  - Supports **free-tier cloud APIs** (**Groq**, **Google Gemini**, **OpenRouter `:free` models**) via `.env` or the UI **Provider Switcher** modal for sub-second streaming.
- **Recruiter Observability UI**:
  - **Live Trace & Latency Inspector** drawer (`Memory ms`, `Router ms`, `Search ms`, `TTFT ms`, `Total ms`, recalled memories, and `web_search` cache/provider telemetry).
  - **Memory Timeline** sidebar tab grouping past questions chronologically with live FTS5 search.

---

## Quickstart (Single Command)

### Option 1: Local Free Setup (Ollama + Zero-Key DuckDuckGo)

Prerequisites: Python 3.11+, Node 20+, [`uv`](https://docs.astral.sh/uv/), and [Ollama](https://ollama.com/) (or a free Groq/Gemini API key).

```powershell
# 1. Clone & enter repo
git clone https://github.com/jackyToras/kairo.git
cd kairo

# 2. Optional: copy .env.example -> .env (works with 0 edits if Ollama is running!)
copy .env.example .env

# 3. Run one-command startup (installs deps, builds frontend, serves on port 8000)
.\start.ps1
```

On macOS / Linux:

```bash
chmod +x start.sh
./start.sh
```

Then open **http://localhost:8000** (FastAPI API docs at **http://localhost:8000/docs**).

### Option 2: Ultra-Fast Free Cloud Demo (Groq or Gemini Free Tier)

For sub-second token streaming during live demos at $0 cost:
1. Get a free API key from [Groq Console](https://console.groq.com) or [Google AI Studio](https://aistudio.google.com).
2. Either set it in `.env`:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_...
   ```
   **OR** click the **Provider button** in the top-right corner of the Kairo UI and paste the key in-memory without restarting the server.

### Option 3: Docker

```bash
docker build -t kairo .
docker run -p 8000:8000 -v kairo_data:/app/data kairo
```

---

## Development Mode (Hot Reload)

```powershell
# Terminal 1: FastAPI backend
.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000

# Terminal 2: Vite React frontend
cd frontend
npm run dev
```

---

## Tests, Linting & Evaluations

```powershell
# Run unit + FastAPI SSE integration tests (12 tests)
.venv\Scripts\pytest.exe -v

# Run Ruff linter
.venv\Scripts\ruff.exe check backend tests evals

# Run reproducible evaluation suite (temporal memory, routing, 1-tool invariant + live DDG search)
.venv\Scripts\python.exe evals\run_evals.py --live
```

Latest verified benchmark results (see [`DESIGN.md`](./DESIGN.md)):
- **Tests:** 12 / 12 passed
- **Temporal Memory Eval:** 5 / 5 (100%, p50 `5.47 ms`, p95 `10.54 ms`)
- **Router & Single-Tool Invariant:** 9 / 9 (100%, p50 `0.02 ms`, `tool_count = 1`)
- **Live DuckDuckGo Search + Top-3 Page Extraction:** `~2.97 s` uncached, `~9.5 ms` cached

---

## 60-Second Video Recording Script

Use this exact timed flow while screen-recording **http://localhost:8000** with the **Trace** drawer visible:

- **0:00 – 0:12 (Hook & Constraint):** *"I built Kairo—a fast, source-grounded chat agent in FastAPI and React with strictly one tool: `web_search`. Notice in the Trace Inspector: `tool_schema_count = 1`—memory and routing live in the orchestrator, not extra tools."*
- **0:12 – 0:28 (Accuracy & Live Search):** Click **"Live Web Grounding"** (e.g., *"Who created the FastAPI Python framework?"* or *"What is the latest FastAPI release?"*). Point out the live SSE phases (`Searching web` -> `Synthesizing`), inline `[1]` citations, expandable source excerpts, and `search_ms` in the Trace drawer.
- **0:28 – 0:45 (Speed & Temporal Memory — "What & When"):** Click **New Chat** (proving cross-session memory!), then ask *"What did I ask you earlier today and when?"*. Highlight `route_mode: memory_recall`, `0` web searches executed, `memory_recall_ms`, and the **Memory Timeline** tab on the left showing exact timestamps.
- **0:45 – 0:60 (Why & Engineering Rigor):** Briefly flash `DESIGN.md` and mention the SQLite WAL + FTS5 + RRF hybrid retrieval, concurrent page extraction with prompt-injection sanitization, 100% free local/cloud LLM support, and the `pytest` + `evals` suite.
