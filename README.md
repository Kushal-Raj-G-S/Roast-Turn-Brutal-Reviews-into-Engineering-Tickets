# Roast 🔥

**Turn app store reviews into engineering tickets — automatically.**

Roast ingests raw user reviews, clusters them by semantic similarity, runs LLM-powered Root Cause Analysis, and exports structured tickets straight to GitHub Issues or Linear. Built for mobile teams who are drowning in feedback but starved for signal.

**Live at → [roast.systems](https://roast.systems)**

---

## ☕ Support the Developer

[![Buy Me A Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://buymeacoffee.com/kushal.raj.gs)

---

## The Problem

Product teams get thousands of app store reviews. Most tooling just shows you a star rating. Roast goes further — it reads every review, groups them by **what's actually broken**, assigns severity, and drafts a ready-to-file bug report with a machine-generated root cause hypothesis.

No manual tagging. No spreadsheets. Just actionable tickets.

---

## What You Can Do (Full Feature List)

### 📤 Upload & Ingest
- Drag-and-drop any reviews CSV (up to 500 MB) from Google Play, App Store, or custom exports
- Schema intelligence auto-detects 13+ column formats — no mapping required
- Live progress during processing: total reviews ingested, noise filtered, clusters created
- Supports up to **100,000 reviews per file** on paid plans

### 🤖 AI Analysis Pipeline
- **Noise filtering** — strips generic praise ("great app!"), reviews under 25 chars, and spam patterns before analysis
- **Semantic clustering** — groups reviews by what's actually broken using `all-MiniLM-L6-v2` embeddings (384-dim vectors, cosine similarity)
- **Severity scoring** — every cluster gets automatically classified as `CRITICAL / HIGH / MEDIUM / LOW`
- **Regression detection** — flags if a previously-resolved issue has resurfaced in the latest batch (Jaccard similarity ≥ 0.40 across your upload history)
- **Velocity spike detection** — alerts when a cluster grows 1.5σ above baseline with ≥ 15 reviews in the window
- **Adversarial detection** — identifies coordinated spam campaigns, duplicate bot reviews, and template injection attacks

### 📋 Root Cause Analysis (RCA)
Async LLM job generates a structured **7-section RCA** for every CRITICAL and HIGH cluster:
1. Hypothesis
2. Affected surface
3. Reproduction steps
4. Diagnostic checklist
5. Suggested fix
6. Prevention
7. Notes

Powered by a multi-provider LLM chain (DeepSeek R1 → DeepSeek V3 → LLaMA 4 → GPT → Groq fallback) with circuit breakers so analysis never stalls.

### 📊 Analytics Dashboard
- Full severity distribution (CRITICAL / HIGH / MEDIUM / LOW counts)
- Status distribution (`fresh_roast → assigned → in_progress → resolved / wont_fix`)
- Expandable cluster cards — view sample reviews, affected versions & devices, keywords
- Upload history with per-upload cluster previews and delete (cascading)
- Kanban board view (up to 50 live tickets across status columns)

### 🔬 AI Debug Center *(Pro+ only)*
- Per-severity category summaries — "here's what all your CRITICAL issues have in common"
- Per-cluster on-demand triage note: root cause, affected surface, reproduction signal, recommended first action
- Copy full structured prompt to send to any LLM for deeper analysis

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
| `crash / performance / login / payment` | Full 7-section RCA bug report |
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
| AI / Embeddings | `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace Inference API · TF-IDF + LSA fallback |
| LLM Chain | DeepSeek R1 · DeepSeek V3 · LLaMA 4 · GPT-OSS-120B · Groq fallback |
| Frontend | Next.js 14 (App Router) · TypeScript · Tailwind CSS · Framer Motion |
| Database | PostgreSQL (Supabase) · ChromaDB (optional, vector store) |
| Auth | Supabase Auth (email / Google / GitHub OAuth) |
| Infra | Heroku (backend) · Vercel (frontend) · Supabase (DB + auth) |

---

## How It Works

```
CSV Upload → Schema Detection → Noise Filter → Semantic Embedding
     → Cosine Clustering → Severity Classification
     → Shadow Deployment (v1 ‖ v2 ‖ v3 drift monitor in parallel)
     → Regression Detection → Spike Detection
     → Async LLM RCA Generation → Severity Summaries
     → Export to GitHub / Linear / CSV / PDF / Markdown
```

1. **Upload** — any CSV dropped in; schema auto-detected, plan limits checked
2. **Filter** — drops reviews ≥ 4 stars with no negative keywords, generics, <25 char reviews, and spam
3. **Embed** — HuggingFace Inference API (zero torch on server); falls back to TF-IDF + SVD LSA locally
4. **Cluster** — NearestNeighbors cosine similarity (threshold 0.3), batch size 128
5. **Shadow run** — v2 pipeline + drift monitor run in parallel; Jaccard comparison catches silent regressions
6. **RCA** — 4 parallel async LLM tasks: one category summary per severity + deep RCA for top CRITICAL/HIGH clusters
7. **Export** — any of 5 formats, any cluster, instantly

---

## Key API Endpoints

```
POST   /upload                                    Upload CSV, starts full pipeline
GET    /uploads                                   List uploads (paginated)
GET    /uploads/{id}/progress                     Live processing status + metrics
GET    /uploads/{id}/clusters                     All clusters for an upload
GET    /uploads/{id}/severity-explanations/{sev}  AI category summary (poll while pending)
GET    /clusters/{id}                             Full cluster detail (RCA, reviews, keywords)
GET    /clusters/{id}/explain                     On-demand triage note (LLM, max 25 reviews)
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

- **Shadow Deployment** — every upload runs v1 + v2 pipelines in parallel; outputs compared via Jaccard similarity; significant divergence logged as an alert
- **Drift Monitoring** — v3 subprocess checks for score distribution shifts (>0.5 mean shift) and adversarial patterns (>5% duplicate rate) per upload
- **LLM Circuit Breakers** — 3 failures → model blocked for 300s (A4F), 2 failures → 120s (Groq); rotates automatically across 9 models
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
DATABASE_URL         Supabase PostgreSQL connection string
A4F_API_KEY          Primary LLM provider (A4F) key
GROQ_API_KEY         Groq fallback LLM key
HUGGINGFACE_API_KEY  Embeddings via HuggingFace Inference API
```

---

## Deploy (Production)

**Backend → Heroku**
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Frontend → Vercel**
```
NEXT_PUBLIC_API_URL=https://your-backend.herokuapp.com
```

---

## Project Structure

```
/backend
  app/
    api/          Route handlers (upload, clusters, export)
    services/     Embedding, clustering, RCA, LLM, noise filter
    models/       SQLModel schemas (Upload, Cluster, Profile, Usage)
    workers/      Async background worker (poll loop, LLM tasks)
    core/         Config, plans enforcement, shadow deployment, memory
    routes/       Auth + plan routes
  src/            v2 domain-driven architecture (DI, use cases, entities)
  migrations/     SQL migration scripts
/frontend
  src/
    app/          Next.js App Router pages (dashboard, upload, analytics,
                  ai-debug, clusters, pricing, settings, login, docs)
    components/   KanbanBoard, TicketExportModal, UsageDashboard, SpotlightCard
/dataset          25+ real app review CSVs (Instagram, WhatsApp, TikTok, Spotify…)
                  + adversarial test sets (bot campaigns, spam, corrupted data)
```

---

## ☕ Support

[![Buy Me A Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://buymeacoffee.com/kushal.raj.gs)

---

MIT License
