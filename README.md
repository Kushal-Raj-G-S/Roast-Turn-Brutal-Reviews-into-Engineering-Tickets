  # Roast 🔥

  **Turn app store reviews into engineering tickets — automatically.**

  Roast ingests raw user reviews, clusters them by semantic similarity, runs an **agentic LLM pipeline** for Root Cause Analysis (with retrieval over past resolved issues and automated quality scoring), and exports structured tickets straight to GitHub Issues or Linear. Built for mobile teams who are drowning in feedback but starved for signal.

  **Live at → [roast.systems](https://roast.systems)**

  ---

  ## The Problem

  Product teams get thousands of app store reviews. Most tooling just shows you a star rating. Roast goes further — it reads every review, groups them by **what's actually broken**, assigns severity, and drafts a ready-to-file bug report with an AI-agent-generated, retrieval-grounded root cause hypothesis — scored for how well it's actually supported by the evidence.

  No manual tagging. No spreadsheets. Just actionable tickets.

  ---

  ## What You Can Do (Full Feature List)

  ### 📤 Upload & Ingest
  - Drag-and-drop any reviews CSV (up to 500 MB) from Google Play, App Store, or custom exports
  - Schema intelligence auto-detects 13+ column formats — no mapping required
  - **Size-aware processing screen** — a 5-stage tracker (filter → embed → cluster → severity → AI RCA) paced by the file's own real review count, not a generic spinner, plus rotating pipeline facts so a multi-minute job on a large file doesn't feel stuck
  - Supports up to **100,000 reviews per file** on paid plans (tested up to 900k+ raw rows)

  ### 🤖 AI Analysis Pipeline
  - **Text dedup before embedding** — exact + normalized (case/whitespace-insensitive) duplicate reviews are embedded once and re-expanded, cutting redundant embedding work on large uploads
  - **Noise filtering** — strips generic praise ("great app!"), reviews under 25 chars, and spam patterns before analysis
  - **Semantic clustering** — groups reviews by what's actually broken using local `all-MiniLM-L6-v2` embeddings (384-dim vectors, cosine similarity), run through an **ONNX int8-quantized** model for faster CPU inference
  - **Scale-adaptive indexing** — FAISS `IndexFlatIP` (exact) for smaller uploads, automatically switches to `IndexHNSWFlat` (approximate nearest-neighbor) above 100k reviews so very large uploads don't stall on O(n²) similarity search
  - **Severity scoring** — every cluster gets automatically classified as `CRITICAL / HIGH / MEDIUM / LOW`
  - **Regression detection** — flags if a previously-resolved issue has resurfaced in the latest batch (Jaccard similarity ≥ 0.40 across your upload history)
  - **Velocity spike detection** — alerts when a cluster grows 1.5σ above baseline with ≥ 15 reviews in the window
  - **Adversarial detection** — identifies coordinated spam campaigns, duplicate bot reviews, and template injection attacks

  ### 🧠 Agentic Root Cause Analysis (RCA)
  Every CRITICAL and HIGH cluster is analyzed by a **multi-step LangGraph agent**, not a single LLM call:

  1. **Investigate** — reads the cluster's sample reviews
  2. **Retrieve similar** — hybrid search (dense vector + BM25 keyword, fused with Reciprocal Rank Fusion, reranked with a cross-encoder) over every previously-resolved cluster, to check "have we seen this before?"
  3. **Hypothesize** — drafts a root-cause hypothesis, explicitly flagging if it looks like a regression of a past issue
  4. **Critique** — a second LLM pass adversarially checks the draft against the evidence: what's unsupported, what alternative was overlooked
  5. **Finalize** — produces a schema-validated structured result (via function-calling, not free-text parsing): hypothesis, likelihood, affected surface, reproduction steps, diagnostic checklist, suggested fix, prevention notes, confidence score

  Then **RAGAS evaluation** scores the final hypothesis for **Faithfulness** and **Answer Relevancy** against the actual review text — so you can see whether an explanation is well-supported by evidence or speculative, not just take the model's word for it. Every run is traced end-to-end (Langfuse if configured, otherwise a local trace log) with a `trace_id` you can inspect.

  Runs on NVIDIA NIM (`meta/llama-3.1-8b-instruct`) as the single, verified-fast model — with a plain single-shot fallback if the agent pipeline ever fails, so RCA generation never goes fully silent.

  ### 📊 Analytics Dashboard
  - Full severity distribution (CRITICAL / HIGH / MEDIUM / LOW counts)
  - Status distribution (`fresh_roast → assigned → in_progress → resolved / wont_fix`)
  - Expandable cluster cards — view sample reviews, affected versions & devices, keywords
  - **Agent analysis panel** per cluster — the reasoning pipeline, precedent found, faithfulness/relevancy score bars, and why
  - **Recurring-issue badges**, **evidence-support badges** (well-supported vs. speculative — verify manually), and **severity-adjustment badges** when the agent's suggested severity differs from the assigned one
  - Sentiment-aware top-signal card — won't mislabel a positive-sentiment cluster as a "complaint"
  - Live "AI analysis still running" banner while the background agent pass completes
  - Upload history with per-upload cluster previews and delete (cascading)
  - Kanban board view (up to 50 live tickets across status columns)

  ### 🔬 AI Debug Center *(Pro+ only)*
  - Per-severity category summaries — "here's what all your CRITICAL issues have in common," with clickable evidence citations that jump to and expand the exact cluster being referenced
  - **Live Playground** — run the actual RCA prompt against the live model yourself, right in the browser: pick a "model style" persona (16+ family presets — Meta, DeepSeek, Qwen, GLM, Mistral, Google, NVIDIA, and more), set the temperature, and get a genuinely differently-structured answer (step-by-step reasoning vs. terse vs. hedged vs. ranked-list, depending on style) — backed by one fast, verified model so it never hangs on an uninvokable model ID. Copy the result or reset back to the default prompt any time.

  ### 📥 Export — 5 Formats

  | Format | What gets exported | Where |
  |---|---|---|
  | **CSV** | All clusters — title, severity, status, review count, regression flag, RCA hypothesis, affected versions/devices, keywords, top 3 sample reviews | Downloads to browser |
  | **PDF** | Same data as CSV in print-ready formatted layout with aggregated stats table | Browser print dialog |
  | **GitHub Issues** | Full markdown ticket posted directly via GitHub API using your personal access token | Your repo's Issues tab |
  | **Linear** | Issue created via Linear GraphQL API using your API key — priority mapped from severity | Your Linear team |
  | **Markdown** | Clipboard-ready formatted ticket with severity badge, signal strength, cluster type, RCA, 8 user quotes with ratings | Clipboard |

  Each export intelligently branches by cluster type:

  | Cluster Type | Routing |
  |---|---|
  | `crash / performance / login / payment` | Full RCA bug report |
  | `feature_request` | PM backlog format with user voice quotes |
  | `complaint` | UX team format with impact assessment |
  | `positive` | Product signal — not filed as a bug |
  | `ad / gameplay / ui / bug` | Type-specific labels and descriptions |

  ---

  ## Pricing

  5 tiers — enforced at upload time (HTTP 402 with error codes `UPLOAD_LIMIT_REACHED` / `REVIEW_LIMIT_EXCEEDED`):

  | Plan | Uploads / Month | Max Reviews / File | Price |
  |---|---|---|---|
  | **Free** | 5 | 20,000 | $0 |
  | **Starter** | 10 | 50,000 | $10 / mo |
  | **Pro** | 50 | 100,000 | $25 / mo |
  | **Business** | 100 | 100,000 | $49 / mo |
  | **Enterprise** | Unlimited | Unlimited | Custom |

  - **AI Debug Center** is Pro+ only
  - **Enhanced CSV/PDF export with AI debug info** is Pro+ only
  - Monthly usage resets per calendar month; track remaining quota on your dashboard

  ---

  ## Authentication

  - Email + password signup/login
  - **Google OAuth** one-click sign-in
  - **GitHub OAuth** one-click sign-in
  - All auth via Supabase — JWTs, refresh tokens, session management handled automatically

  ---

  ## Stack

  | Layer | Tech |
  |---|---|
  | Backend | FastAPI · Python 3.13 · SQLModel · SQLAlchemy |
  | Embeddings | Local `sentence-transformers/all-MiniLM-L6-v2` (ONNX int8-quantized, CPU) — HF Inference API and TF-IDF+SVD as fallback tiers |
  | Agentic RCA | LangGraph (multi-step agent) · Instructor (schema-validated structured output) · RAGAS (Faithfulness / Answer Relevancy scoring) |
  | Retrieval / Memory | Qdrant (embedded, on-disk vector store) + BM25, fused with Reciprocal Rank Fusion, cross-encoder reranked |
  | Observability | Langfuse (optional) with local JSONL trace-log fallback |
  | LLM | NVIDIA NIM (`meta/llama-3.1-8b-instruct`) via the OpenAI-compatible SDK |
  | Frontend | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS · Framer Motion |
  | Database | PostgreSQL (Supabase) |
  | Auth | Supabase Auth (email / Google / GitHub OAuth) |
  | Infra | DigitalOcean (backend) · Vercel (frontend) · Supabase (DB + auth) |

  ---

  ## How It Works

  ```
  CSV Upload → Schema Detection → Noise Filter → Dedup → Local Embedding (ONNX)
      → Scale-Adaptive Clustering (FAISS flat / HNSW) → Severity Classification
      → Shadow Deployment (v1 always; v2 comparison sampled/off by default)
      → Regression Detection → Spike Detection
      → LangGraph RCA Agent (investigate → retrieve → hypothesize → critique → finalize)
      → RAGAS Quality Scoring → Vector-Store Indexing (for future precedent)
      → Severity Summaries
      → Export to GitHub / Linear / CSV / PDF / Markdown
  ```

  1. **Upload** — any CSV dropped in; schema auto-detected, plan limits checked
  2. **Filter** — drops reviews ≥ 4 stars with no negative keywords, generics, <25 char reviews, and spam
  3. **Dedup + Embed** — exact/normalized text dedup, then local ONNX-quantized MiniLM embeddings (falls back to HF Inference API or TF-IDF+SVD if the local model can't load)
  4. **Cluster** — cosine similarity via FAISS, exact below 100k reviews, HNSW approximate above it
  5. **Shadow run** — v1 always runs and is the source of truth; the v2 architecture comparison run is disabled by default (env-gated) since it doubles processing time and has consistently validated as equivalent — flip it back on with `SHADOW_V2_ENABLED` when re-validating an architecture change
  6. **RCA agent** — for each CRITICAL/HIGH cluster: retrieve similar past issues, hypothesize, self-critique, finalize a structured result, score it with RAGAS, index it back into the vector store as future precedent
  7. **Export** — any of 5 formats, any cluster, instantly

  For the full detailed diff against the previous single-shot-LLM architecture — what changed, why, and the real bugs it fixed — see **[NEW_ARCHITECTURE_CHANGES.md](NEW_ARCHITECTURE_CHANGES.md)**.

  ---

  ## Key API Endpoints

  ```
  POST   /upload                                    Upload CSV, starts full pipeline
  GET    /uploads                                   List uploads (paginated)
  GET    /uploads/{id}/progress                     Live processing status + metrics
  GET    /uploads/{id}/clusters                     All clusters for an upload
  GET    /uploads/{id}/severity-explanations/{sev}  AI category summary (poll while pending)
  GET    /clusters/{id}                             Full cluster detail (RCA, ai_metadata, reviews, keywords)
  GET    /clusters/{id}/explain                     On-demand triage note (LLM, max 25 reviews)
  POST   /clusters/{id}/playground                  Ad-hoc prompt/persona/temperature experiment (Debug Center)
  GET    /user/plan                                 Current plan + usage + limits + reset date
  POST   /user/plan                                 Update plan
  POST   /auth/signup                               Create account
  POST   /auth/login                                Login
  POST   /auth/google                               Google OAuth
  GET    /auth/me                                   Current user profile
  GET    /health                                    API health
  GET    /health/db                                 Connection pool diagnostics
  ```

  ---

  ## Reliability & Observability

  - **Shadow Deployment** — v1 runs on every upload as the source of truth; the v2 architecture comparison run is env-gated (`SHADOW_V2_ENABLED` / `SHADOW_V2_SAMPLE_RATE`) rather than run on every upload, since it's proven equivalent (match_score consistently 1.00) and doubles processing time
  - **Drift Monitoring** — v3 subprocess checks for score distribution shifts (>0.5 mean shift) and adversarial patterns (>5% duplicate rate) per upload, when v2/v3 are enabled
  - **Failed uploads no longer get stuck** — a v1 processing failure now marks the upload `failed` with an error message instead of leaving it spinning at "processing" forever
  - **LLM Retry Control** — transient NVIDIA request failures retry with short backoff; a real client-side timeout is enforced (15s) so a hanging/invalid model can't block a request indefinitely; the app returns a safe fallback message if the provider stays unavailable
  - **RCA never goes fully silent** — if the LangGraph agent pipeline fails for any reason, generation falls back to a plain single-shot LLM prompt
  - **Rate-limit self-throttling** — a shared, singleton-enforced sliding window (35 req/60s) keeps every LLM caller under NVIDIA's account limit rather than reacting to 429s after the fact
  - **DB Connection Pool** — pool_size=10, max_overflow=20, pool_timeout=10s, pool_recycle=300s; monitored via `GET /health/db`
  - **Exponential Backoff** — worker retries DB failures with 5→10→20→40→80→120s cap; disposes pool on failure

  ---

  ## Quick Start (Local)

  ```bash
  # Backend (Python 3.13+, Node 18+ required)
  cd backend
  python -m venv venv && .\venv\Scripts\activate   # Windows
  pip install -r requirements.txt
  uvicorn app.main:app --reload                     # → localhost:8000

  # Frontend
  cd frontend
  npm install
  npm run dev                                       # → localhost:3000
  ```

  **Required environment variables:**
  ```
  DATABASE_URL         Supabase PostgreSQL connection string (no default — the app
                        will refuse to start without it; never commit a real value)
  NVIDIA_API_KEY       NVIDIA NIM API key
  ```

  **Optional environment variables:**
  ```
  HUGGINGFACE_API_KEY  Only used if EMBEDDING_BACKEND=hf_api is explicitly set
                        (local ONNX embedding is the default, no key needed)
  EMBEDDING_BACKEND    torch | hf_api — override the default local ONNX embedding path
  SHADOW_V2_ENABLED    true to always run the v2 comparison pipeline (default: false)
  SHADOW_V2_SAMPLE_RATE  e.g. 0.1 to sample v2 on 1-in-10 uploads instead of all/none
  LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY  Enable Langfuse tracing for the RCA agent
                        (falls back to a local JSONL trace log if unset)
  ```

  ---

  ## Deploy (Production)

  **Backend → DigitalOcean**
  ```
  web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

  **Frontend → Vercel**
  ```
  NEXT_PUBLIC_API_URL=https://your-backend.ondigitalocean.app
  ```

  ---

  ## Project Structure

  ```
  /backend
    app/
      api/          Route handlers (upload, clusters, export, playground)
      services/     Embedding, clustering, RCA, LLM, noise filter
        ai/         LangGraph RCA agent, structured output, hybrid-search
                    vector store, RAGAS evaluation, tracing/observability
      models/       SQLModel schemas (Upload, Cluster, Profile, Usage)
      workers/      Async background worker (poll loop, LLM tasks)
      core/         Config, plans enforcement, shadow deployment, memory
      routes/       Auth + plan routes
    src/            v2 domain-driven architecture (DI, use cases, entities)
    migrations/     SQL migration scripts
    export_schema_snapshot.py     Dump live DB schema (no data) for backup/cloning
    restore_schema_from_snapshot.py  Replay a schema snapshot onto a fresh Supabase project
  /frontend
    src/
      app/          Next.js App Router pages (dashboard, upload, analytics,
                    ai-debug, clusters, pricing, settings, login, docs)
      components/   KanbanBoard, TicketExportModal, UsageDashboard, SpotlightCard,
                    AgentAnalysisPanel, BrandIcons, PipelineScrollWorld (landing hero)
  /dataset          25+ real app review CSVs (Instagram, WhatsApp, TikTok, Spotify…)
                    + adversarial test sets (bot campaigns, spam, corrupted data)
  ```

  MIT License
