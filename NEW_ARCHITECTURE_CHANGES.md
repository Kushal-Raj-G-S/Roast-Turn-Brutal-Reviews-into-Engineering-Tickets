# What Changed — Old Architecture vs. Current Architecture

This document is a full, technical, no-summarizing account of everything that changed in this codebase versus the previous committed architecture. It exists so anyone (including future-me) can understand *exactly* what moved, why it moved, and what bug or limitation it fixed — not just "AI stuff got better."

It's organized by subsystem. Each section states the **old behavior**, the **new behavior**, and the **reason** (quoting the actual in-code comments where the reasoning was written down at the time, since those are the most trustworthy record of intent).

---

## 1. Embedding pipeline

**File:** `backend/app/services/bulk_embedding.py`

### Old
Two-tier design that deliberately avoided `torch` entirely:
- Tier 1 (default whenever a key was present): HuggingFace Inference API — hosted `sentence-transformers/all-MiniLM-L6-v2`.
- Tier 2 (fallback): sklearn TF-IDF + TruncatedSVD, fitted **once per process** and cached in module-level globals (`_TFIDF_VECTORIZER` / `_TFIDF_SVD`) behind a `threading.Lock`, reused across every upload that hit the fallback path.
- `get_global_model()` was a dead stub that never returned anything real.
- The file's own comment stated the intent explicitly: *"torch / sentence-transformers are intentionally NOT imported anywhere. They are removed from requirements.txt to prevent accidental installation."*

### New
Re-architected to **local-first, best-quality-first**, now three tiers:

- **Tier 0 (default):** local `sentence-transformers/all-MiniLM-L6-v2`, CPU-only, loaded once per process. Tries a **pre-quantized int8 ONNX export** first (`onnx/model_quint8_avx2.onnx`, via `optimum[onnxruntime]`), falling back to plain torch if the ONNX load fails for any reason.
  - Benchmarked and documented in-line: *"~20-25% faster than plain torch on a 4000-review batch, same output shape/quality."*
  - AVX2 build chosen deliberately over AVX-512: *"AVX2 is present on effectively every x86_64 CPU made since ~2013... unlike AVX-512, which many modern consumer chips disable."*
  - `max_seq_length` capped to 128 tokens (`EMBEDDING_MAX_SEQ_LENGTH` env var): *"App store reviews are short... Capping this to 128 measurably cuts CPU encode time on large uploads (200k+ reviews)."*
  - `torch.set_num_threads(os.cpu_count() or 4)` is now set explicitly, because left at its default it *"can silently sit at 1 thread depending on how the process was launched (e.g. under uvicorn --reload)"* — a real, silent performance bug that would otherwise make embedding single-threaded without any error or warning.
  - Escape hatches for debugging/ops: `EMBEDDING_BACKEND=torch` skips the ONNX path; `EMBEDDING_BACKEND=hf_api` forces the old hosted-API tier.
- **Tier 1 (now opt-in only):** HF Inference API — same model, hosted. Previously the *default* path whenever a key existed; now only used if `EMBEDDING_BACKEND=hf_api` is explicitly set.
- **Tier 2 (fallback):** sklearn TF-IDF + SVD — now **fits fresh on every call** instead of reusing a cached singleton. This reverses the old caching behavior on purpose, because it was a **latent correctness bug**: *"the vocabulary must come from the upload being processed, not from whatever unrelated upload happened to run first on this server process."* Two different uploads sharing one process could previously have their TF-IDF vocabulary silently cross-contaminated.
- `get_global_model()` is no longer a stub — it returns the actually-loaded local model.

### Why this matters in practice
This is the single biggest lever behind the "why does a 200k-row CSV take so long" performance work from earlier in the project: it removes a network round-trip per embedding batch (HF Inference API), replaces it with a faster-than-baseline local CPU path, and fixes a thread-count bug that could have silently left the embedder running on a single core.

---

## 2. Bulk upload processing

**File:** `backend/app/services/bulk_processor.py`

Three independent, unrelated fixes landed in this file:

### 2a. Dedup before embedding
**Old:** every review row, including exact and near-exact duplicates, was individually embedded.
**New:** before embedding, each review's text is normalized (`re.sub(r"\s+", " ", t.strip().lower())`), deduplicated via `np.unique(..., return_inverse=True)`, only the unique texts are embedded, and the result is re-expanded to the original row count via `unique_embeddings[inverse_indices]`.
**Why:** *"the embedding model's tokenizer is uncased (bert-base-uncased vocab), so 'Good app' / 'good app' / 'GOOD APP ' already produce the same embedding — deduping only exact strings was leaving free dedup on the table."* On a real large upload with many near-duplicate low-effort reviews ("Good app", "nice", "👍"), this measurably cuts embedding work for free — no accuracy tradeoff, since those strings would embed identically anyway.

### 2b. Session rollback on failure
**Old:** the exception handler tried to mark an upload as `failed` directly, without first rolling back the SQLAlchemy session.
**New:** `self.session.rollback()` is called *before* attempting the failure-recovery write.
**Why:** SQLAlchemy requires an explicit rollback after a failed flush/commit (e.g. a dropped DB connection mid-transaction), or the recovery query itself raises `PendingRollbackError` — meaning the upload was previously left stuck at its last in-progress status **silently, forever**, with no error surfaced anywhere. This was a real production bug: uploads that hit a transient DB blip would just hang in the UI indefinitely.

### 2c. FAISS index selection by scale
**Old:** always used `IndexFlatIP` — exact brute-force cosine similarity, O(n²).
**New:** if `n > 100,000` reviews (`_HNSW_THRESHOLD`), switches to `IndexHNSWFlat(d, 32, METRIC_INNER_PRODUCT)` with `efConstruction=40`, `efSearch=64` — an approximate nearest-neighbor index that trades a small amount of recall for dramatically better scaling.
**Why:** concrete benchmark numbers are recorded in-line: *"100k → flat 19s vs HNSW 26s; 150k → flat 128s vs HNSW 44s"*, and *"A 226k-review upload was observed stalling on this exact step for many minutes."* Below 100k rows, flat search is actually a bit faster and stays exact, so the threshold keeps small/medium uploads on the exact path.
**Bug this introduced and then fixed in the same change:** HNSW can return `-1` for unfilled neighbor slots when there are fewer than `k` real neighbors. The union-find clustering loop that consumes these indices previously would treat `-1` as "the last element" via Python's negative-indexing semantics — silently merging unrelated reviews into the wrong cluster. Fixed by guarding every neighbor-index use with `if j >= 0 and dist <= threshold`.

---

## 3. LLM provider — full rewrite

**File:** `backend/app/services/llm_service.py`

### Old: multi-provider cascading fallback
- **A4F API** as primary, with a `ModelProvider` enum of 5 models (`deepseek-r1-0528`, `deepseek-v3.1-tee`, `deepseek-v3`, `llama-4-maverick`, `gpt-oss-120b-tee`), each wrapped in its own `CircuitBreaker` (3 failures → 300s block).
- **Groq** as secondary fallback, 4 models (`llama-3.3-70b-versatile`, `llama-4-maverick-17b-128e-instruct`, `qwen3-32b`, `llama-3.1-8b-instant`), its own circuit breaker (2 failures → 120s block).
- Raw `httpx.AsyncClient` calls to each provider's REST endpoint.
- Rate limiting was explicitly disabled: `rate_limit = 100` with a comment noting it was set for "max speed," effectively unlimited.

### New: single verified provider
- **NVIDIA's OpenAI-compatible endpoint** (`NVIDIA_API_URL`, default `https://integrate.api.nvidia.com/v1`; `NVIDIA_MODEL`, default `meta/llama-3.1-8b-instruct`) via the official `openai` SDK's `AsyncOpenAI` client.
- All circuit-breaker and multi-model-fallback machinery removed — there is one provider, one model, kept simple and observable rather than "resilient" across five different unreliable third-party APIs.
- **Rate limit tightened to 35 requests/60s**, deliberately below NVIDIA's actual account limit: *"NVIDIA's free-tier account limit is 40 requests/min (confirmed by the client) — 35 leaves headroom so we self-throttle BEFORE hitting NVIDIA's own 429s, instead of just reacting to them."* This only works because every caller goes through the same singleton (`get_llm_service()`), so all concurrent callers see the same sliding window — a fresh `LLMService()` instance would start an empty window and defeat the whole point.
- **A dead-code timeout bug fixed:** `self.timeout = 15.0` was previously declared but *never actually passed to the HTTP client*. With no client-side timeout, a hanging or invalid model ID could block for the SDK's own default (10 minutes) instead of 15 seconds. Found while testing the new Debug Center playground against several bad model IDs — one hung a test script for minutes before the root cause was traced. Fixed by wiring it into the client constructor: `AsyncOpenAI(base_url=self.api_url, api_key=self.api_key, timeout=self.timeout)`.
- **`generate()` gained new optional parameters:** `model`, `temperature`, `persona_label` — added specifically to power the new AI Debug Center playground (section 6 below). The docstring is explicit about a real finding from direct testing: *"most model ids on NVIDIA's public catalog are NOT invokable on every account/key... an earlier version of the debug-center playground called `model=` directly with 19 'popular' ids and 16 of them 404/410'd or hung, wasting real time on every single run."* `persona_label` is the safe alternative: it never touches the real API `model=` field, it only flavors the system prompt so the one real, fast, verified model writes in a different voice.
- **New `_persona_style_instructions(persona_label)`** — maps a model-family name to a concrete, followable *structural* behavior instead of a vague "sound like X" instruction, because *"'Write like {name}' alone is too vague for a small model to actually act on — it can't imitate a model it's never seen."* Ten family-specific rules (step-by-step reasoning for DeepSeek/QwQ/R1-style names, terse for Mistral/Mixtral, hedged/cautious for Gemma/Google, confident/direct for GPT-OSS/OpenAI, systems-terms framing for Nemotron/NVIDIA, ranked-list enumeration for GLM/Zhipu, conversational for Kimi/Moonshot, formal/enterprise for Granite/IBM, two-angle consideration for Jamba/AI21, balanced for Yi/Qwen) plus a generic fallback.
- **New `_temperature_instruction(effective_temperature)`** — similarly concrete tiers: ≥0.6 exploratory (names at least one unconventional explanation), ≥0.35 moderate speculation allowed, else strict/literal (no speculation beyond the evidence).
- Both instructions are only appended to the system prompt when the caller explicitly passed a persona or overrode temperature — i.e. **only the Debug Center playground ever sees this text.** Production RCA calls pass neither, so this change is provably invisible to the main product pipeline.
- `FALLBACK_MESSAGE` promoted from an inline string to an exported module constant, specifically so other new code (`evaluation.py`, section 6) can detect "the call failed and returned the sentinel" vs. "the model actually said this" — this distinction turned out to matter (see section 6.4).

---

## 4. RCA / severity-summary pre-generation

**File:** `backend/app/services/explanation_pregenerate.py`

- Both `pregenerate_for_upload` and `pregenerate_rca_for_clusters` switched from directly instantiating `LLMService()` to calling `get_llm_service()` — required so the shared rate-limiter state described in section 3 is actually shared, rather than each call site accidentally getting its own private, un-throttled instance.
- **Major addition:** `_generate_rca_for_one_cluster` now runs the new LangGraph agent pipeline (section 6) as the **primary** path, with the previous single-shot `_build_rca_prompt` + `llm.generate()` call kept as an **explicit fallback** — the design goal stated in-line: *"RCA generation should never go fully silent just because one of the newer AI components hiccups."*
  - Calls `run_rca_agent(...)`; if it returns a `final_rca`, also runs RAGAS evaluation (`evaluate_rca`) using the cluster's sample reviews as ground-truth context.
  - `_format_structured_rca(agent_result)` flattens the agent's structured output back into the **existing** three free-text database columns (`rca_hypothesis` / `rca_steps` / `rca_fix`) — a deliberate choice: *"no schema migration needed, and the existing frontend already renders these as-is."* The generated markdown includes the likelihood/scope/severity assessment, a "Similar issues found (hybrid search + reranking)" precedent block, an "AI Quality Score (RAGAS)" line when eval scores are available, and a footer crediting the agent pipeline with its confidence percentage.
  - `_build_ai_metadata(agent_result)` separately builds the new **structured** JSON persisted to `Cluster.ai_metadata` (section 8) — kept apart from the markdown specifically so the frontend can render real UI elements (badges, score bars) instead of regexing prose out of a markdown string.
  - On any exception from the agent pipeline, falls back to the original single-shot prompt/generate path unchanged from before — old behavior is fully preserved as the safety net.
  - After a successful RCA (agent or fallback), the cluster is **best-effort indexed into the vector store** (`vector_store.index_cluster`) inside its own isolated try/except, so future uploads can retrieve it as precedent — explicitly designed to *never block RCA persistence* if indexing fails.

---

## 5. New API surface

**File:** `backend/app/api/bulk_routes.py`

- `ClusterDetailResponse` and `get_cluster_details` now expose the new `ai_metadata` field (section 8).
- **New endpoint: `POST /clusters/{cluster_id}/playground`** — the entire backend for the new AI Debug Center Playground feature.
  - Request: `{ prompt, model?, temperature?=0.2, max_tokens?=600 }`. Response: `{ output, model_used, persona_used, temperature_used }`.
  - Always calls the one configured, verified-fast NVIDIA model — **never** routes `payload.model` directly into the real API `model=` field. It's passed through as `persona_label` instead (see section 3).
  - Server-side clamps: `temperature` to `[0.0, 1.0]`, `max_tokens` to `[1, 1000]`.
  - Validates the cluster exists (404 if not) and the prompt is non-empty (400 if empty).
  - Explicitly documented as ephemeral: nothing here is written back to the cluster's stored `rca_hypothesis`/`ai_metadata` — it's a scratch space, safe to experiment freely without corrupting real data.

---

## 6. New subsystem: the agentic RCA pipeline

**Directory:** `backend/app/services/ai/` (entirely new)

This is the largest architectural addition. The old RCA path was one LLM call: build a prompt from a cluster's sample reviews, call `generate()`, store the raw text. The new path is a 5-node LangGraph agent with real tool use (retrieval), self-critique, schema-validated output, and automated quality scoring.

### 6.1 `rca_agent.py` — the orchestrator
Defines an `RCAState` (TypedDict) threaded through a `StateGraph` (compiled once, cached in `_compiled_graph`) with five linear nodes:

1. **`investigate`** — formats up to 5 sample reviews from the cluster into a structured evidence block.
2. **`retrieve_similar`** — a genuine tool call into the new vector store: `vector_store.hybrid_search(query=title, top_k=3, exclude_cluster_id=...)`, to find precedent from clusters that were already resolved in the past.
3. **`hypothesize`** — an LLM call (max_tokens=400) drafting a 3–5 sentence root-cause hypothesis from the evidence + similar-issues context, explicitly instructed to flag if a similar past issue suggests this is a regression.
4. **`critique`** — a *second, independent* LLM call (max_tokens=300) that adversarially critiques the draft hypothesis against the evidence: what's unsupported by the actual reviews, what alternative explanation got overlooked.
5. **`finalize`** — calls `generate_structured_rca()` (section 6.2) to produce a validated `StructuredRCA` object that incorporates the draft, the critique, and the original evidence. On failure, `final_rca` is `None` and the caller (section 4) falls back to the old plain-text path.

Every node is wrapped in a `trace.span(...)` context manager for observability (section 6.5). Public entrypoint: `run_rca_agent(cluster_id, title, severity, app_name, platform, reviews, keywords)` — starts a trace, invokes the compiled graph, returns `{final_rca, hypothesis_draft, critique, similar_issues, trace_id}`.

**Why an agent instead of one call:** the old single-shot prompt had no way to check its own work, no memory of past resolved issues, and no structural guarantee the output was even parseable. The self-critique step exists specifically to catch hallucinated or evidence-unsupported claims before they're finalized, and the retrieval step exists so the same bug reported twice, months apart, gets flagged as a likely regression instead of analyzed from scratch each time.

### 6.2 `structured_rca.py` — schema-validated output
Defines the actual output contract as Pydantic models:
- `RootCauseHypothesis` — likelihood, scope, explanation, suggested_severity, severity_reason.
- `AffectedSurface` — booleans/flags across client_ui / client_logic / network_api / backend_service / config_experiments.
- `StructuredRCA` (top level) — hypothesis, affected_surface, reproduction_steps (list), diagnostic_checklist (list), suggested_fix, prevention, notes, confidence (float 0–1).

`generate_structured_rca(prompt, max_retries=2)` wraps `instructor.from_openai(AsyncOpenAI(...), mode=instructor.Mode.TOOLS)`. TOOLS mode (native function-calling) was chosen deliberately over JSON mode: *"far more reliable than JSON mode for smaller models like an 8B instruct model — JSON mode occasionally had the model echo the schema itself back instead of filling it in."* Called with `temperature=0.2, max_tokens=1800`.

**This is a real correctness improvement over the old approach:** the old RCA text was free-form markdown with no validation — if the model produced malformed output, it would just get stored and shown to the user as-is. The new path structurally cannot produce a result that doesn't match the schema; Instructor retries automatically on validation failure.

### 6.3 `vector_store.py` — semantic memory for resolved issues
A hybrid-search retrieval-augmented-generation (RAG) stack, built from scratch:
- **Qdrant**, embedded and on-disk (`./qdrant_data`, collection `resolved_clusters`, 384-dim cosine vectors matching MiniLM's output dimension) — chosen specifically because it needs **no server process**, keeping the whole thing self-contained and free to run.
- **BM25** (`rank_bm25.BM25Okapi`) sparse/keyword search over the same corpus, tokenized with a simple `[a-z0-9]+` regex — catches exact-term matches that pure semantic search can miss (e.g. a specific error code or feature name).
- **Reciprocal Rank Fusion** (`k=60`, the standard `1/(k+rank+1)` formula) merges the dense and sparse rankings into one combined score, rather than picking one method or the other.
- **Cross-encoder reranking** (`cross-encoder/ms-marco-MiniLM-L-6-v2`, lazily loaded only when first needed) re-scores the fused top-10 candidates directly against the raw query text for a more precise final top-`k` (agent uses `top_k=3`, UI default is 5).
- `index_cluster(cluster)` — upserts a cluster's title + keywords embedding plus payload (title, severity, status, keywords, rca_hypothesis, rca_fix, review_count) into Qdrant. Called after every successful RCA (agent or fallback path), so the store grows with every resolved cluster over time.
- `hybrid_search(query, top_k=5, exclude_cluster_id=None)` — returns a ranked list of `SimilarIssue` records. Explicitly designed to degrade gracefully: returns `[]` on an empty or unavailable store, since this is *"a 'have we seen this before' lookup, not a hard dependency"* — retrieval failing should never block RCA generation.
- **Known, documented scaling limit:** BM25 re-scans the *full corpus* on every call. Fine at current scale (a few thousand resolved clusters at most); the code comments flag this explicitly as something to swap for a persistent BM25 index if the corpus ever grows past that.

### 6.4 `evaluation.py` — automated RCA quality scoring
Uses **RAGAS** to score every finalized RCA hypothesis against the actual review evidence:
- `evaluate_rca(issue_title, hypothesis_text, review_contexts)` computes two metrics — **Faithfulness** (is the hypothesis actually supported by the evidence?) and **Answer Relevancy** (is the hypothesis actually about the issue?) — via `ragas.metrics.collections.Faithfulness` / `AnswerRelevancy`, both rounded to 3 decimals, backed by `ragas.llms.InstructorLLM` (wrapping the same NVIDIA/Instructor client, so no second provider or extra cost) and `ragas.embeddings.HuggingFaceEmbeddings` (the same local MiniLM model, CPU).
- A **third** LLM call, `_generate_score_reasoning`, asks the model to explain in 1–2 sentences *why* it scored the way it did, tied concretely to the cluster's actual hypothesis and evidence — so a low score isn't just a bare number, it comes with a reason a human reviewer can act on.
- **A specific correctness check that mattered in practice:** `if reasoning == FALLBACK_MESSAGE: return None`. Because `generate()` never raises on failure — it returns the sentinel fallback string instead (section 3) — without this check, a failed reasoning call would get stored and displayed to the user *as if it were a real explanation of the score*. This is the exact reason `FALLBACK_MESSAGE` was promoted to an importable constant.
- The entire module is best-effort by design: any exception anywhere returns `None` rather than raising, because *"a failed eval shouldn't take down RCA generation."*

### 6.5 `observability.py` — agent tracing
Two-tier design:
- **Tier 1 (if configured):** Langfuse — full trace UI with steps, prompts, outputs, latency, and cost, activated only if both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set.
- **Tier 2 (always-on fallback):** a local JSONL log at `./traces/rca_traces.jsonl` — zero setup, zero account required, so tracing works out of the box even with no Langfuse account configured.
- The `Trace` class exposes `.span(name, input_data)` as a context manager (records duration, input, and output per span — this is what every node in `rca_agent.py` wraps itself in) and `.finish(output)`, which writes the JSONL record, closes the Langfuse trace if active, and returns a `trace_id` (UUID) that gets threaded all the way out to `ai_metadata.trace_id` and shown in the UI.
- `_safe()` truncates any logged payload to 2000 characters, so a pathologically long review or model output can't blow up the trace log.

---

## 7. Shadow deployment — v2 comparison run is now gated, not automatic

**Files:** `backend/app/core/shadow_deployment.py`, `backend/shadow_orchestrator_real.py`

### Old
Every upload ran v1 synchronously, then **always** kicked off v2 asynchronously, waited for it, and ran a full comparison. If both succeeded, v3 drift/adversarial monitoring also ran. This effectively doubled the total processing time of every single upload, since v2 re-runs the entire embedding + clustering pipeline from scratch on a separate architecture.

### New
v2 (and, consequently, v3) is now **disabled by default**, controlled by two new env vars:
- `SHADOW_V2_ENABLED=true` — always run v2, like the old behavior.
- `SHADOW_V2_SAMPLE_RATE` — e.g. `"0.1"` samples v2 on roughly 1-in-10 uploads instead of all-or-nothing.

When v2 is skipped, the code synthesizes a trivial `ExecutionMetrics`/`ComparisonResult` (`match_score=1.0`, `differences={"skipped": "v2 disabled -- see SHADOW_V2_ENABLED"}`) so downstream code that expects a comparison result doesn't need special-casing.

**Why:** stated directly in-line — *"v2 doubles total processing time (it re-runs the full embedding + clustering pipeline from scratch), and it's only worth paying that cost while still validating the v2 architecture against v1. Every real upload tested has come back match_score=1.00 — v2 is proven equivalent, so it's disabled by default."* This was a direct fix for the "why does processing take so long" performance investigation — v2 was silently doubling wall-clock time on every upload for a comparison that had already been validated as always-matching.

### Also in this area
- `upload.processing_time_seconds` is now recorded (`round(v1_metrics.duration_ms / 1000, 2)`), feeding the frontend's new "Analyzed in Xs" display (section 9.2).
- **Stuck-upload bug fixed:** previously, a v1 processing failure only logged a warning and left `upload.status` untouched — the frontend would show that upload spinning as "processing" forever, with no way for a user to know it had actually failed. Now the failure branch sets `status = "failed"`, records `error_message` (from the pipeline error, truncated to 500 chars, or a generic message), sets `completed_at`, and commits.

---

## 8. Schema changes

**File:** `backend/app/models/bulk_models.py`

`Cluster` gained a new JSON column: `ai_metadata: Optional[Dict[str, Any]]`. Documented shape:
```
{
  likelihood, scope, suggested_severity, severity_reason, confidence,
  similar_issues: [{title, severity, status}],
  eval_scores: {faithfulness, answer_relevancy},
  trace_id,
  agent_steps: [str]
}
```
Kept deliberately separate from the existing free-text `rca_hypothesis`/`rca_steps`/`rca_fix` columns — *"so the frontend can render real badges/meters instead of regexing prose."* This is what powers every new badge and score bar described in section 9.2.

---

## 9. Frontend changes

### 9.1 AI Debug Center (`frontend/src/app/(app)/ai-debug/page.tsx`)

- **The old "Prompts" tab is retired entirely** and replaced by a new **"Playground"** tab. The old tab just showed a static, pre-built debug prompt with a copy-to-clipboard button — functionally redundant with what the new tab does strictly better.
- **New `PlaygroundPanel`** — a genuinely live LLM experimentation UI:
  - A single textarea holds either the editable default RCA prompt or, after running, the result **in place** (replace, not side-by-side) — a deliberate UX choice so the workflow is "try the default, don't like it, tweak model/temp, run again" rather than juggling two panes.
  - A custom-built "model style" combobox (not a native `<datalist>`, which turned out to render inconsistently and couldn't be styled) — 16 entries across Meta/OpenAI/DeepSeek/Qwen/GLM/Moonshot/Mistral/Google/Microsoft/NVIDIA families, grouped visually by family. Explicitly documented in the UI/API layer as **not a real model switch** — see section 3's `persona_label` design. Every selection sent as `persona_label`, never as `model=`.
  - A genuinely-applied temperature slider (0–1, step 0.1).
  - "Run" calls the new `POST /clusters/{id}/playground` endpoint (section 5), refreshing the Supabase session token first so long-open tabs don't send a stale token.
  - Result header shows `model_used` (the real model that ran) vs. `persona_used` (the chosen style) vs. `temperature_used`, so it's honest about what actually happened server-side.
  - "Reset prompt" restores the original default prompt text; "Copy" (merged in from the retired Prompts tab) copies whatever's currently in the box.
- **`ExplanationPanel` gained clickable evidence citations** — cluster titles that appear verbatim in generated explanation prose (the generation prompt feeds the model these exact titles and asks it to reference them, so they reliably show up unmodified) are detected via a dynamically-built regex (all cluster titles, longest-first to avoid partial-match collisions) and rendered as clickable buttons. Clicking one selects and scrolls that exact cluster into view on the left, so a claim in the AI's summary can be checked against the real review text backing it in one click, instead of taking the summary on faith.

### 9.2 Analytics page (`frontend/src/app/(app)/analytics/page.tsx`)

- **New AI-enrichment-pending banner + poller** — the agent+RAGAS pass runs as a background phase after the page already shows raw clusters (and only covers the top 5 CRITICAL/HIGH clusters per upload). A new poller checks the `clusters` table every 5s (up to 12 times, ~1 minute) until `ai_metadata` has landed for the eligible clusters, or gives up and shows a clear "taking longer than usual (API rate limit) — reload in a bit" message instead of silently looking finished when it isn't.
- **New `AgentAnalysisPanel`** rendered per-cluster when `ai_metadata` is present — shows the agent's reasoning pipeline, likelihood/scope/suggested-severity, precedent found via hybrid search, and the RAGAS Faithfulness/Answer-Relevancy scores as visual bars.
- **New per-cluster badges**, all derived from `ai_metadata`:
  - 🔁 **RECURRING** when `similar_issues.length > 0`, with a tooltip listing the precedent.
  - ✓ **WELL-SUPPORTED BY EVIDENCE** (emerald) when `eval_scores.faithfulness >= 0.5`, otherwise ⚠ **SPECULATIVE — VERIFY MANUALLY** (yellow) — the honest, visible signal that some AI explanations go beyond what the reviews directly state, instead of presenting every hypothesis with equal, unearned confidence.
  - **SEVERITY ADJUSTED: X → Y** (sky) when the agent's suggested severity differs from the stored one, with the reasoning in a tooltip.
- **"#1 User Complaint" card sentiment fix** — a new positive/negative word-regex heuristic detects when the top LOW-severity cluster is actually praise, and relabels the card "#1 Top Signal" (emerald) instead of "#1 User Complaint" (red/orange) — *"calling that a 'complaint' is actively wrong, not just imprecise."* This was found and fixed twice: once as a real bug (a positive cluster mislabeled), and once flagged as a possible false alarm that on inspection turned out to be a genuinely negative review, correctly labeled.
- **New processing-time display** — `analytics.upload_data.processing_time_seconds` (section 7) shown next to the review count with a clock icon.

### 9.3 Upload page (`frontend/src/app/(app)/upload/page.tsx`)

- **Progress-poller token-refresh fix** — the poller now calls `supabase.auth.getSession()` (which refreshes if needed) and re-sets the API token before *every* poll, not just once at upload start. Long jobs (200k+ reviews) can outlive the access token's 1-hour lifetime; previously the poller kept using the token captured at upload start, causing a wall of silent 401s partway through a long-running job.
- **Consecutive-failure give-up threshold** — after 10 consecutive poll failures (~20s of failures), the UI poll stops entirely instead of hammering the backend indefinitely. The job itself keeps running server-side regardless; this only stops the *client-side* polling.

### 9.4 API client (`frontend/src/lib/api-client.ts`)

- New types `AgentSimilarIssue`, `AgentMetadata` mirroring the new `ai_metadata` shape from section 8.
- New method `runPlayground(clusterId, {prompt, model?, temperature?, max_tokens?})` → `POST /clusters/{id}/playground`.

### 9.5 Other frontend changes (dependency-driven, not feature work)

- **Brand icon replacement** (`login/page.tsx`, `(marketing)/page.tsx`, `MarketingFooter.tsx`, `TicketExportModal.tsx`) — `lucide-react`'s `Chrome`/`Github`/`Twitter` icons were dropped upstream in `lucide-react` v1 (bumped from `0.562.0` → `1.34.0`), which removed all trademarked brand logos. A new `frontend/src/components/ui/BrandIcons.tsx` provides local inline-SVG replacements (`GoogleIcon`, `GithubIcon`, `XIcon`).
- **`middleware.ts` → `proxy.ts` rename** — tracks a Next.js framework naming convention change (this project pins a pre-release/newer Next.js build; see `frontend/AGENTS.md`, which documents that this Next.js version has breaking API changes vs. older training data and should be read before making framework-level changes). Only the exported function name changed (`middleware` → `proxy`); the actual Supabase server-client/cookie logic is untouched.
- **PhoneMockup hero animation rewrite** (`frontend/src/components/landing/PhoneMockup.tsx`) — the scroll-driven landing-page phone demo now measures its own content height at runtime via `ResizeObserver` instead of using a hardcoded scroll distance, so the pinned-scroll section always ends exactly when the content finishes revealing. Also added: spring-smoothed scroll progress, scroll-velocity-driven motion blur, cursor-reactive 3D tilt, a redesigned lock screen with a slide-and-defocus unlock animation, real SVG status-bar icons (signal/Wi-Fi/battery) replacing placeholder bars, and a Dynamic-Island-style camera notch.
- `frontend/src/components/ui/Preloader.tsx` — swapped the fire-emoji placeholder logo for the actual `/logo.png` brand asset.
- `frontend/src/app/api/proxy/user/plan/route.ts` — extended its backend-URL fallback chain to also check `NEXT_PUBLIC_API_URL`, matching what the rest of the frontend already uses.

---

## 10. Security fix: hardcoded database credentials removed

**File:** `backend/app/core/config.py`

**Old:** `DATABASE_URL` had a hardcoded fallback containing a **real, working Supabase connection string with an embedded plaintext password**, committed directly in source.

**New:** `DATABASE_URL = os.getenv("DATABASE_URL")`, with no fallback. If it's unset, the app raises `RuntimeError("DATABASE_URL environment variable is not set. Set it in your .env file (see README.md).")` at import time instead of silently falling back to a credential that shouldn't be in source control at all.

This is a genuine security fix, not a style change — the old code shipped a working database password in the git history.

---

## 11. New operational tooling

**New files:** `backend/export_schema_snapshot.py`, `backend/restore_schema_from_snapshot.py`

- `export_schema_snapshot.py` — connects to the live Supabase/Postgres DB and dumps a **schema-only** JSON snapshot (tables, columns, constraints, indexes, triggers, and public functions, across `public` + `auth` schemas by default) to `schema_snapshot.json`. No row data is ever exported.
- `restore_schema_from_snapshot.py` — replays that snapshot onto a **fresh** Supabase project, public schema only. Deliberately skips Supabase-managed `auth` tables, since those are created and maintained by Supabase itself and shouldn't be hand-replicated. Supports `--dry-run` for a safe preview before `--apply`.

**Why this exists:** disaster-recovery and environment-cloning — being able to stand up a new Supabase project with the identical schema (tables, constraints, indexes) without hand-writing migrations or exporting/restoring real user data.

---

## 12. Dependency changes

### Backend (`requirements.txt`) — new packages

| Package | What it's for |
|---|---|
| `openai>=2.54.0,<3.0.0` | The OpenAI-compatible SDK client used for the NVIDIA endpoint (section 3) and Instructor's structured output (section 6.2). Pinned below 3.x because Instructor/langchain-openai don't yet support the openai 3.x line. |
| `sentence-transformers>=5.1.0` | Local embedding model (section 1) and the cross-encoder reranker (section 6.3). |
| `torch>=2.9.0` | Runtime backing sentence-transformers — reintroduced deliberately, reversing the previous "zero torch" policy. |
| `optimum[onnxruntime]>=1.23.0` | The ONNX int8-quantized inference path for faster CPU embedding. |
| `langgraph>=1.2.11` | The RCA agent's `StateGraph` orchestration (section 6.1). |
| `qdrant-client>=1.19.0` | Embedded on-disk vector store for resolved-cluster precedent (section 6.3). |
| `rank_bm25>=0.2.2` | Sparse/keyword retrieval, fused with dense search via RRF. |
| `instructor>=1.15.4` | Schema-validated structured LLM output (sections 6.2, 6.4). |
| `langfuse>=4.14.0` | Optional agent tracing (section 6.5). |
| `ragas>=0.4.3` | Faithfulness/Answer Relevancy scoring (section 6.4). |
| `langchain-community==0.4.1` (exact pin) | A dependency ragas needs for legacy `chat_models` compat shims that a newer langchain-community version (0.4.2+) dropped. |

`chromadb` was **removed entirely** — superseded by Qdrant for the new vector-store use case.

Existing dependencies were also bumped significantly across the board (FastAPI, uvicorn, pydantic, pandas, numpy, SQLAlchemy, faiss-cpu, supabase-py, and others) to their latest compatible versions.

### Frontend (`package.json`)

| Package | Change | Why |
|---|---|---|
| `lucide-react` | `0.562.0` → `1.34.0` (major) | Forced the new `BrandIcons.tsx` component — v1 dropped trademarked brand logos. |
| `next` | `16.1.1` → `16.3.2` | Framework upgrade; also the trigger for the `middleware.ts` → `proxy.ts` rename. |
| `framer-motion` | `12.26.2` → `13.1.1` | Powers the new PhoneMockup spring/velocity/tilt interactions and AgentAnalysisPanel animations. |
| `@supabase/ssr` | `0.8.0` → `0.12.5` | Compatibility with the Next.js version bump. |
| `react` / `react-dom`, `@types/node`, `eslint`, `eslint-config-next`, `typescript` | Minor/patch bumps | Routine version tracking alongside the Next.js upgrade. |

---

## 13. Upload progress screen — honest, size-aware pacing (2026-08-27)

**Files:** `frontend/src/app/(app)/upload/page.tsx`, `backend/app/api/bulk_routes.py`

### Old
The processing screen showed a static spinner, a hardcoded "Processing Your Reviews" title, and a progress bar bound to `progress.progress` — a field the `/uploads/{id}/progress` endpoint never actually returns. In practice this animated from `0%` to `undefined%` (visible as a broken/blank bar in the browser console: *"You are trying to animate width from '0%' to 'undefined%'"*) and sat there, unchanged, for the entire multi-minute job. `total_reviews`/`filtered_noise`/`clusters_created` were also only ever populated on the Upload DB row **atomically at the very end** of processing, alongside `clusters_created` — meaning the frontend had zero real incremental signal to show during the actual wait.

### New
- **`bulk_routes.py`**: the pre-flight row count (already computed on every upload for plan-limit enforcement, then previously discarded) is now stored on the `Upload` row as `total_reviews` at creation time — before any processing happens. This is later overwritten with the exact final count by `shadow_deployment.py` once processing completes, so there's no conflict, just an earlier, real, approximate number available immediately.
- **`upload/page.tsx`**: the progress bar is now driven by an elapsed-time estimate that **scales with that real review count** (`~21ms/review`, calibrated from an actual local run: 15,000 reviews ≈ 5.3 min end-to-end), instead of a fixed time constant. This was a deliberate fix for a real failure mode caught in testing: a fixed-time curve would race ahead of reality on a large upload — e.g. showing 90%+ complete while a 200k-review file was still deep in the embedding step alone, actively misleading the user into thinking it was nearly done when it wasn't. The curve is asymptotic and capped at 96% (never claims done until `status === 'completed'` actually arrives), so if the real job runs longer than the estimate, the bar just creeps rather than lying.
- A 5-stage tracker (filter → embed → cluster → severity → AI RCA), each stage keyed to a real pipeline step and a percentage range of the estimate, replaces the single static label — with a step-checklist UI (checkmarks fill in as stages pass), a small flame-icon tally next to the heading, ambient decorative embers around the stage icon, and a rotating 4-second tip ticker with genuine facts about the pipeline (dedup, semantic clustering, self-critiquing agent, regression checks) rather than filler copy.
- Review-count/kept/cluster stat tiles now always render (with `—` placeholders) instead of being hidden entirely until data lands at the very end.

### Why this matters
Verified against two real large uploads during testing: a 15k-review file (which the original time constant was tuned against) and a 200k-review file, where the fixed-time version would have shown a badly misleading near-complete bar. The size-aware version keeps the estimate honest at both ends — quick files still feel responsive, and a 200k-review job (observed taking 15–20+ min locally, CPU-only, no GPU) shows a bar that paces itself accordingly instead of finishing visually in under 5 minutes.

---

## 14. Marketing landing page — hero replaced with a scroll-driven "pipeline world" (2026-08-27)

**New file:** `frontend/src/components/landing/PipelineScrollWorld.tsx`
**New assets:** `frontend/public/scroll-world/scene-{1..6}.webp`, `frontend/src/fonts/raleway.ts` + `frontend/src/fonts/raleway/*.ttf`
**Touched:** `frontend/src/app/(marketing)/page.tsx`

### Old
The marketing page's hero was `PhoneMockup` (section 9.5) — a scroll-driven phone demo (lock screen → Play Store → reviews scrolling with pop-in annotations).

### New
`PhoneMockup` is replaced by `PipelineScrollWorld`: six AI-generated isometric diorama stills (dark glossy low-poly tech miniatures, ember-orange/red-on-black, matching Roast's own brand palette) mapped one-to-one to the six real stages the backend actually runs on a batch of reviews — Inbox (ingest) → Filter (noise removal) → Constellation (semantic clustering) → Tower (severity ranking) → War Room (the agentic RCA pipeline from section 6) → Ticket (export). As the visitor scrolls through a pinned 6×170vh section, the current scene crossfades into the next with a slow Ken-Burns push-in, and a bottom-pinned copy block (eyebrow / headline / body, set in a self-hosted **Raleway**, scoped to just this component via `next/font/local` — not added to the site's global font stack) swaps in sync with whichever scene is dominant. A right-edge dot rail shows scroll position; `useReducedMotion()` swaps the whole thing for a plain stacked-sections fallback with no scroll-jacking.

Stills were generated through Codex's `$imagegen` tool (OpenAI image generation) from a shared style preamble (fixed palette, "isometric low-poly diorama, near-black background, glowing flame emblem present in every scene") so the six scenes read as one consistent world rather than six unrelated illustrations, then converted to WebP (~60-120KB each, down from ~1.3-2MB PNGs) via `ffmpeg`.

### Bugs hit and fixed during the build (kept here because most of them explain real, non-obvious Framer Motion / browser behavior, not just "AI made a mistake")

- **Scene 1 invisible at scroll-top.** The first attempt drove each scene's opacity off four hand-computed keyframes (`fadeIn, bandStart, bandEnd, fadeOut`) per scene, clamped with `Math.max(0, ...)` / `Math.min(1, ...)` at the array's own edges. For index 0, `fadeIn` and `bandStart` both clamped to exactly `0` — a duplicate keyframe input, which `useTransform` can't resolve unambiguously, leaving the very first scene stuck transparent.
- **A genuine runtime crash** (`Cannot read properties of undefined (reading 'get')`, thrown inside `SceneLayer`) turned out to be the actual root cause of most of the visually-wrong behavior seen while iterating (the finale logo bleeding into the wrong scene's band, an earlier scene staying visible under the wrong heading) — a broken render tree left React showing stale DOM from before the crash while state elsewhere kept updating normally, which looked like inconsistent scroll math but wasn't. Root-caused by not trusting the first (plausible-looking) theory and instead confirming via `document.hidden`/console history that earlier "it's just uncomposited-tab throttling" explanations didn't hold up once tested on a clean tab.
- **Fixed by replacing all of the per-scene keyframe math with one closed-form trapezoid** — `opacity` for scene *i* is a function of `|scenePosition - i|` alone (`scenePosition` being a single continuous `0..N-1` value derived once from `scrollYProgress`), expressed via the standard 4-point array `useTransform` overload with keyframes `[i - halfWidth, i - plateau, i + plateau, i + halfWidth]`. Because these are just `i` offset by fixed constants — never clamped against a shared 0/1 boundary — there is nothing left for index 0 or index `N-1` to collide with; the crash did not recur after this rewrite.
- **Scene 6 never loading.** All six scene `<img>` layers occupy the identical `position: absolute; inset: 0` box (only `opacity` differs), so the browser's native `loading="lazy"` — which decides by viewport distance — couldn't distinguish them and silently never fired for one of them, leaving an earlier scene's image stuck rendered underneath the last scene's (correct) pinned copy. Fixed by loading all six eagerly; six small WebP files at hero-scale is not something lazy-loading was meaningfully saving anyway.
- **Diorama stills reading as solid black.** The generation art-direction (small floating island on a `#0a0a0a` background) is fine for a compact thumbnail but, stretched full-bleed as a hero background, the frame is mostly near-black by design — combined with a dark bottom gradient for text legibility, several scenes were reading as an empty black rectangle rather than a rendered image. Fixed with a `brightness(1.65) contrast(1.15) saturate(1.2)` CSS filter on every scene image, and by shrinking the legibility gradient to only darken near the very bottom instead of the whole frame.
- **`logo.png` pixelation at hero scale.** The finale scene briefly used the site's actual brand mark (`/logo.png`) instead of AI-generated art, per a request to make the brand connection unmistakable. `logo.png` is a deliberately pixel-art 500×500 asset — crisp as a small nav icon, but visibly blocky stretched to 600-800px+. Capped its display size to 160-224px and set `image-rendering: pixelated` so the pixel art reads as an intentional style rather than a blurry upscale. (The finale scene was ultimately reverted to use its own AI-generated diorama art instead of the logo, for visual consistency with the other five scenes — the logo swap and the sizing/rendering fix both remain available if that decision changes again.)

### Why this matters
The old hero demoed the product's *UI* (a phone showing the app). The new one demoes the product's *pipeline* — the actual sequence of things Roast does to a batch of reviews, narrated scene-by-scene, so the value proposition is legible before a visitor ever signs in.

---

## 15. Closing the loop — fix verification, fused triage, alerting, repro stubs (2026-08-27)

**New files:** `backend/app/services/notifications.py`, `backend/app/services/ai/repro_stub_generator.py`, `backend/migrations/add_fix_verification_and_alerts.sql`
**Touched:** `backend/app/core/shadow_deployment.py`, `backend/app/api/bulk_routes.py`, `backend/app/models/bulk_models.py`, `backend/app/models/models_supabase.py`, `frontend/src/lib/api-client.ts`, `frontend/src/app/(app)/analytics/page.tsx`, `frontend/src/app/(app)/settings/page.tsx`

Up to this point the product ran strictly one direction — reviews in, ticket out — and then forgot. Everything in this section closes a loop instead of adding another forward pipeline stage.

### 15.1 Fix verification loop (the differentiator)

**Old:** `_detect_regressions` already existed, comparing each new cluster's title against the user's previously-**resolved** clusters using token-level **Jaccard overlap** at a 0.40 threshold. Stored a bare boolean (`regression_detected`) plus the matched title.

**New:** the same function now *also* computes **semantic cosine similarity** between new and resolved clusters, using the pipeline's own local embedding backend (`bulk_embedding.EmbeddingBackend` — no network call, no API cost, same model already loaded for clustering). Either signal crossing its threshold flags a regression; three new columns record *how sure* and *which signal caught it*:

- `regression_confidence` (float) — `max(jaccard, semantic)`
- `regression_match_method` — `keyword` | `semantic` | `keyword+semantic`
- `regression_resolved_at` — when the *original* cluster was marked resolved

**Why this specifically:** Jaccard structurally cannot match a paraphrase. Measured on real embeddings during the build:

| new cluster | previously resolved | Jaccard | semantic | caught by |
|---|---|---|---|---|
| "App crashes on login" | "App freezes when signing in" | **0.00** | **0.708** | semantic only |
| "Video playback stutters badly" | "Videos keep buffering and lagging" | **0.00** | **0.709** | semantic only |
| "Cannot upload profile picture" | "Photo upload fails every time" | **0.12** | **0.672** | semantic only |
| "App crashes on login" | "Dark mode colors look wrong" | 0.00 | 0.120 | (correctly rejected) |
| "Battery drains fast" | "Great app love the new update" | 0.00 | 0.066 | (correctly rejected) |

All three real paraphrase pairs were **completely invisible** to the pre-existing keyword matcher and are now caught, with a wide clean gap (0.67+ matches vs ≤0.12 non-matches) around the chosen `_SEMANTIC_REGRESSION_THRESHOLD = 0.62`. The UI badge was relabelled from `REGRESSION` to **`FIX DIDN'T HOLD`** with the confidence percentage inline, because that is the actual claim being made and it's the one competitors can't make.

### 15.2 Confidence-weighted triage queue

**New:** `GET /uploads/{id}/triage-queue`. The pipeline already computed severity, RAGAS faithfulness, the regression signal, and review volume *independently* — but never fused them, leaving engineers to re-derive "what do I fix first" by eye from four separate badges. `_priority_score` combines them: severity weight + `faithfulness × 20` + `30 × regression_confidence` + `log1p(review_count) × 5` (log-scaled so one huge cluster can't drown out everything else).

The ordering this produces is the point — verified against synthetic cases:

```
144.52  critical, 200 reviews, well-supported (faithfulness 0.9)
132.66  high, 50 reviews + REGRESSION (0.9 confidence)   <-- outranks...
130.52  critical, 200 reviews, SPECULATIVE (faithfulness 0.2)  <-- ...this
 87.43  medium, 800 reviews (huge volume, still ranked below real severity)
 33.96  low, 5 reviews
```

A HIGH whose fix demonstrably didn't hold outranking a CRITICAL whose AI explanation isn't evidence-supported is exactly the judgement severity-alone cannot express. Surfaced in the analytics page as a **"By severity" / "⚡ Fix first"** toggle (the toggle only appears once scores have loaded), with the full score breakdown in a hover tooltip so the number is never a black box.

### 15.3 Proactive alerting (Slack / Discord)

**Old:** there was **no outbound notification code anywhere in the backend** — searched, confirmed, zero. Velocity-spike detection existed but only in the v2/v3 shadow path, which is **disabled by default** (§7), so hooking alerts there would have meant alerts that never fire.

**New:** `notifications.py` posts to a Slack incoming-webhook or Discord webhook. One `profiles.alert_webhook_url` field covers both — the payload shape (`{"text":…}` vs `{"content":…}`) is auto-detected from the URL, so the user never has to say which service they're on. Wired into the **v1** (always-on) pipeline for the two events actually worth interrupting someone for: a fix that didn't hold, and a new CRITICAL cluster. Configured in Settings → **Proactive Alerts**, with a "Send test alert" button.

Best-effort by construction: 5s timeout, returns `False` on any failure, never raises — a dead webhook can't affect the upload it's reporting on. Verified: no URL, empty URL, and a syntactically-valid-but-rejected Slack URL all return `False` without raising (the last one round-tripped to Slack's real API, got `404 no_team`, logged a warning, and continued).

### 15.4 Auto-generated repro test stubs

**New:** `POST /clusters/{id}/test-stub` turns `StructuredRCA.reproduction_steps` (already produced by the agent, previously terminal prose) into a runnable **Playwright** skeleton — closing review → ticket → *runnable test*. Reuses the singleton `LLMService`, so it shares the same self-throttled rate limit as every other caller; no new provider or model.

The prompt explicitly forbids inventing selectors/URLs not implied by the bug report, requiring clearly-marked `TODO` placeholders instead — a plausible-looking fake selector is worse than an obvious blank. Unlike RCA generation this **raises rather than falling back**, because there is no safe fallback text for a test stub: a wrong test is worse than no test. Surfaced in the analytics cluster accordion with a Generate/Regenerate button and copy-to-clipboard.

**Security note:** this is the one new endpoint with an explicit ownership check on top of auth. The sibling read-only cluster endpoints are unauthenticated in this codebase, but every call here spends a real LLM request against a shared account rate limit — unauthenticated, anyone could loop over cluster ids and burn the whole account's throughput.

### 15.5 Release-bisected regressions (best-effort)

**New:** `Cluster.affected_versions` exists in the schema but is *never populated* by the live pipeline. However each entry in `sample_reviews` already carries its own `version` (mapped from the CSV's `appVersion`/`app_version`/`version` column). Rather than a pipeline or schema change, `bisect_versions()` derives on read: earliest version, most-common version, distinct count, and a top-5 distribution.

Surveyed against the real database: **10 of 51 completed uploads** carry version data, and on those it resolves for ~18 of 20 clusters — e.g. `{'1.2025.350': 12, '1.2026.006': 7, '1.2025.343': 1}`, a genuinely actionable concentration. Returns `null` (and the UI renders nothing) for the majority of CSVs that have no version column, rather than fabricating a bisect.

### 15.6 Cross-platform bug fusion (best-effort)

**New:** `GET /uploads/{id}/cross-platform-matches` flags cluster pairs that look like one shared-backend issue reported separately on Android and iOS, so it isn't triaged twice as two unrelated client bugs. Uses the existing heuristic `_detect_platform` (regex over title/keywords) to split, then semantic similarity ≥ 0.60 to pair.

Labelled in the UI as *"Same bug on both platforms?"* with an explicit "platform is inferred from review wording, so confirm before merging" caveat — because there is **no structured platform column anywhere in the ingest path** (no `platform`, no `os_version`; device is keyword-matched out of free text). This is deliberately framed as candidates for a human to confirm, not an assertion.

### 15.7 A deployment hazard found and fixed during this work

Adding the five new model columns broke **every** `clusters` and `profiles` query with `UndefinedColumn` until the migration was applied — and because `init_db()` uses `SQLModel.metadata.create_all()`, which creates missing *tables* but never missing *columns*, nothing would have auto-repaired it. Since `get_current_user` queries `profiles`, that would have taken down every authenticated request on deploy, not just the new features. Caught by explicitly querying both tables pre-migration rather than assuming additive model changes are safe. The migration (`add_fix_verification_and_alerts.sql`) is additive and `IF NOT EXISTS`-guarded; it has been applied, and both queries verified working afterwards.

**If deploying this to another environment, run that migration before starting the app.**

A second, quieter version of the same class of problem: the stub generator was originally written as `test_stub_generator.py`, which silently matched the `test_*.py` pattern in `.gitignore` — it would have been absent from a fresh clone and crashed the import at request time, while working perfectly on the machine it was written on. Renamed to `repro_stub_generator.py` rather than adding a `.gitignore` exception, since weakening a broad "don't commit test files" rule to accommodate one production file is the worse trade.

---

## 16. Live testing pass on section 15 — one critical unrelated bug found, two real bugs in the new stub generator fixed (2026-08-27)

**Touched:** `backend/app/services/llm_service.py`, `backend/app/services/ai/structured_rca.py`, `backend/app/services/ai/evaluation.py`, `backend/app/services/ai/repro_stub_generator.py`, `backend/.env` (not committed — gitignored), `frontend/src/app/(app)/settings/page.tsx`

Manually exercising every feature from section 15 against the real database and a real Discord webhook surfaced three genuine bugs — none of them things a type-checker or a syntax check could have caught.

### 16.1 Critical, unrelated: the whole product's LLM model was dead

Clicking "Generate test" for the first time returned a clean error instead of a stub. Root cause traced directly: **`meta/llama-3.1-8b-instruct` — the model hardcoded as the default everywhere in the codebase — reached end-of-life on NVIDIA's side on 2026-08-26 and now returns `410 Gone` on every call.** This wasn't specific to the new stub feature: it silently broke RCA generation, the AI Debug Center playground, and RAGAS evaluation too, the moment NVIDIA flipped the switch.

Queried `GET {NVIDIA_API_URL}/models` for what's actually invokable on this account, then verified candidates against the harder real requirement (Instructor structured/tool-calling output, which RCA generation needs) rather than just "does it answer a prompt":
- `meta/llama-3.2-11b-vision-instruct` — answers plain prompts fine, but returns Llama 3.2's non-OpenAI-compatible `<|python_tag|>{...}` tool-call format, which Instructor cannot parse. Fails the RCA path silently different from how it looks in a quick manual test.
- `nvidia/nemotron-3.5-lightning-30b-a3b` — passed an isolated structured-output test in 5.1s, looked like the obvious "smaller and faster" choice. Measured on the **actual 5-step RCA agent pipeline** (not an isolated call) it was slower and less reliable than the alternative below: 64–118s per cluster, including one outright truncation failure.
- **`nvidia/nemotron-3-super-120b-a12b`** — supports structured output correctly, and despite being the largest model tested, was the fastest and most reliable in the real pipeline once warm: ~22–26s/cluster (a one-time ~48s cost the first time a process loads the cross-encoder reranker doesn't recur per-request).

Fixed the hardcoded default in all three files (was duplicated independently in `llm_service.py`, `structured_rca.py`, `evaluation.py`) to the verified-working model, and documented the tradeoff in-line so a future "let's use the small fast one" instinct doesn't quietly regress this again. `NVIDIA_MODEL` remains an env-var override (in `.gitignore`d `.env`, not committed) for whenever NVIDIA deprecates this one too.

### 16.2 Repro test stub: reasoning leak into the code box

First real generation returned ~6KB of the model's chain-of-thought ("We need to produce a Playwright test... The bug report is extremely vague...") *before* the actual code, despite the prompt explicitly saying "output ONLY the code, no prose before or after." The configured model is a reasoning model and does not reliably follow that instruction. **Fixed by not trusting the instruction** — a regex now extracts just the fenced ` ```typescript ` block from the response; if no complete fenced block is found, the call now raises instead of returning raw reasoning text into what's rendered as a code box in the UI.

### 16.3 Repro test stub: silent truncation on richer clusters

With the code-extraction fix in place, a cluster with more detailed RCA steps failed with "no code block found." Root cause: the original `max_tokens=1400` budget wasn't enough for this reasoning model to *both* think through the problem *and* write a complete file — the response was cut off mid-code with no closing fence, and (correctly, per the fix above) no half-formed code was returned instead of failing outright. Raised to `max_tokens=3000`, which leaves enough headroom for both. Re-verified across 5 different clusters (mix of vague one-line complaints and detailed multi-review reports) with zero truncations afterward.

While fixing this, also acted on direct feedback that the original output was too thin to be useful (a single unstructured `test()` block) — the prompt now asks for a `test.describe` block, a `beforeEach` for shared setup, each action individually commented against the specific RCA step or review quote that justifies it, and one additional grounded edge-case test when the evidence supports it. Still holds the line on the one guardrail that actually matters: never fabricate a selector, URL, or test data not implied by the bug report — `TODO` placeholders only.

### 16.4 A pre-existing stale-token bug, found while testing the alert settings UI

Clicking "Send test alert" in Settings returned `Could not validate credentials: ... token is expired`, even though the user was actively logged in. Root cause: `apiClient` falls back to a token cached in `localStorage` from whatever session last called `setToken()` — every other page that calls the backend directly (e.g. `analytics/page.tsx`) fetches a fresh Supabase session and calls `setToken()` before each call; the new Settings alert UI didn't, so it was silently reusing a long-expired token. Fixed by adding the same `ensureFreshToken()` pattern (calls `supabase.auth.getSession()`, which auto-refreshes, immediately before every alert-settings API call).

### 16.5 Full end-to-end verification of the fix-verification loop (section 15.1)

Rather than trust the unit-level semantic-similarity numbers from section 15.1 in isolation, ran the actual code path against the real database and a real webhook: marked a real resolved cluster (`"[CRITICAL] App crashes"`) as `resolved`, created a new cluster with a paraphrased title (`"the app keeps freezing and shutting down unexpectedly"` — zero shared keywords), ran the real `_detect_regressions`, and confirmed:
- `regression_detected=True`, `regression_confidence=0.801`, `regression_match_method="semantic"` — the keyword matcher alone would have missed this entirely (0.00 Jaccard).
- `_send_upload_alerts` → `notifications.send_alert()` returned `True`, and the message ("🔥 *Roast: fix didn't hold* — ...") was independently confirmed to land in the user's real Discord channel.

Test data (the synthetic cluster and upload) was deleted and the real cluster's `resolved` status reverted afterward — nothing about this verification pass altered real data.

### 16.6 Cross-platform fusion (section 15.6) — confirmed data-limited, not broken

Surveyed all 926 clusters in the live database: the heuristic platform detector fires on only 6 (all Android, 0 iOS). Checked whether this was a regex bug by searching raw review *content* (not just cluster titles) directly: only 8 individual reviews across the whole dataset mention iOS/iPhone/iPad at all, versus 47 mentioning Android — a genuine skew in the underlying data, not a detection failure. The feature is confirmed working exactly as designed (best-effort, returns nothing rather than fabricating a match) — it just won't have much to find until the platform mix in the underlying reviews changes.

---

## 17. Cross-platform fusion: switched from cluster-title scanning to per-review device data (2026-08-27)

**Touched:** `backend/app/api/bulk_routes.py`

Section 16.6 found the title-only platform detector data-limited (0 iOS matches ever, across the whole database) and concluded that was a genuine property of the data, not a bug — true as far as it went, but incomplete: it only checked whether the *raw review text* mentioned a platform, not whether a better signal already existed elsewhere in the schema.

While visually verifying release bisect in the UI, a sample review rendered with an explicit **"Android"** badge — from `sample_reviews[].device`, populated per-review by `bulk_processor.py`'s free-text device-keyword extraction (`_extract_device`), completely separate from `explanation_pregenerate._detect_platform`'s cluster-title regex that cross-platform fusion actually used. Querying it directly: **55 of 926 clusters** have at least one review with a populated `device` field, with real iOS signal the title scanner had zero chance of ever finding: `{Android: 27, Ios: 11, Iphone: 4, Samsung: 7, Oppo: 6, Pixel: 5, Huawei: 4, Realme: 2, Xiaomi: 1}`.

### Old
`get_cross_platform_matches` classified each cluster's platform via `explanation_pregenerate._detect_platform(cluster)` — a regex over the cluster's title and keywords only.

### New
`_detect_platform_from_reviews(cluster)` classifies by scanning every sample review's `device` field against known Android/iOS device-brand words (`samsung/pixel/oneplus/xiaomi/huawei/oppo/vivo/realme/nokia/galaxy/android` vs `iphone/ios/ipad`). `_detect_platform_combined(cluster)` takes the union of this and the original title-based signal — either is enough to tag a cluster, since they're independent evidence sources, not competing guesses. A cluster where one signal says "android" and the other says "ios" (or either alone says "both") is tagged `"both"` and appears as a candidate on each side.

**A cluster tagged `"both"` introduced a real bug during the fix**: it appears in *both* the android and ios candidate lists, so without a guard it matches against itself at cosine similarity 1.0, "discovering" that a cluster is the same bug as itself. Fixed with an explicit `ac.id == ic.id` skip in the pairwise comparison loop, caught before it ever shipped by reasoning through the combined-list construction rather than by a failing test.

### Verified
- Combined detector across the live database: Android detections **6 → 42**, iOS **0 → 12** (one cluster genuinely qualifies for `"both"`).
- The two real android/ios candidate pairs that existed in the account's own uploads were checked and correctly rejected (cosine similarity 0.287 and 0.145 — genuinely unrelated bugs; the fix widens *recall* of candidates, it doesn't relax the *matching* threshold, so it doesn't fabricate matches where none exist).
- No upload in the real data happened to contain a genuine same-bug-different-platform pair to demonstrate a true positive, so one was constructed the same way section 16.5 verified the fix-verification loop: a synthetic Android cluster ("photos fail to upload and app freezes", device=Samsung) and iOS cluster ("cannot upload any picture, app locks up", device=Iphone) describing the same bug in different words. Confirmed rendering live in the analytics UI: **"Same bug on both platforms?" — ANDROID ↔ IOS, 67% similar.** Test upload and both clusters deleted afterward.

---

## 18. Cluster status updates: a missing prerequisite for the fix-verification loop (2026-08-27)

**New:** `PATCH /clusters/{id}/status` in `backend/app/api/bulk_routes.py`
**Touched:** `frontend/src/lib/api-client.ts`, `frontend/src/app/(app)/analytics/page.tsx`

Running the fix-verification loop's checklist item exactly as specified — "mark a cluster resolved in the Kanban board, upload a new CSV, confirm it gets flagged" — surfaced that step one was impossible. `KanbanBoard.tsx` renders fresh/fixing/resolved columns but has no drag-persist logic or API calls at all; `api-client.ts` had `'resolved'` only as a TypeScript union member, never an actual method; the backend had no endpoint to change a cluster's status at all. **There was no way to mark anything resolved anywhere in the product.** Every verification of the fix-verification loop up to this point (sections 15.1, 16.5) had only been possible by editing `status` directly in the database — which meant the flagship feature this session was built around had no real trigger a user could actually reach.

### New
`PATCH /clusters/{id}/status` — validates the target status against the five real values (`fresh_roast | assigned | in_progress | resolved | wont_fix`), enforces the same upload-ownership check as every other cluster-mutating endpoint, and sets `resolved_at`/clears it server-side (not client-supplied) so the regression detector's confidence and timing math stays trustworthy. Reopening a previously-resolved cluster clears `resolved_at`, since it's no longer a valid resolved baseline to compare future uploads against.

Wired into the analytics page as a checkmark button next to the existing ticket-export button on every cluster row (`CheckCircle2`, turns emerald once resolved, click again to reopen) — the Kanban board itself is unchanged and still not wired to persist; this was the minimal real path to unblock the feature rather than a full Kanban rebuild.

### Verified — the full checklist item, for real this time
Rather than re-verify with another database shortcut, ran the exact real flow: clicked the new "Mark as resolved" button on a real cluster (`"[CRITICAL] App crashes"`, id 909) in the live analytics UI, confirmed `PATCH` returned 200 and the button turned emerald; built a small real CSV with paraphrased versions of the same bug ("Application locks up and closes itself...", "The app keeps freezing and shutting down...") and pushed it through the **real** `POST /upload` endpoint with a live session token extracted from the browser (not a synthetic pipeline call — the native OS file-picker dialog itself isn't reachable through this browser-automation surface, so a real authenticated multipart request was used in its place, which exercises the identical backend code path a real browser submission would); waited for the real background worker to finish (4.8s); confirmed both new clusters were flagged **automatically, with no manual `_detect_regressions` call this time** — `regression_detected=True`, confidence 0.713 and 0.63, method `semantic`, `regression_of_title="[CRITICAL] App crashes"`. Confirmed the "2 REGRESSIONS" summary badge and per-cluster "FIX DIDN'T HOLD 71%" / "63%" badges rendered live in the UI, and that hovering surfaced the full tooltip (`"The fix didn't hold. Previously resolved as: ... Match confidence: 71% ... Matched by meaning"`). Also sanity-checked that the pre-existing ticket-export flow was unaffected — the exported markdown correctly included `**⚠️ Regression of:** [CRITICAL] App crashes`. Test upload and cluster status reverted afterward.

---

## 19. Diagnosing a real "test-stub took 64s and failed" report — nested retries and undersized token budgets across the whole AI layer (2026-08-27)

**Touched:** `backend/app/services/llm_service.py`, `backend/app/services/ai/structured_rca.py`, `backend/app/services/ai/evaluation.py`

The user reported the repro-test-stub generator "taking too long and failing," and asked to switch to `openai/gpt-oss-20b` (assuming it would be faster). Rather than switch on assumption, benchmarked it directly first.

### The candidate model, benchmarked rather than assumed
`openai/gpt-oss-20b` **is not faster**: 25.7s at a realistic 1400-token budget (comparable to the current model), and **73.6s** at 3000 tokens -- larger budgets make it slower, not more complete, because it burns 2,300-2,700 tokens per call on hidden reasoning regardless of how much room is available. It does put that reasoning in its own `reasoning_content` API field rather than mixing it into `content` (architecturally cleaner than the current model), but on raw speed it would have made the user's actual complaint worse. Confirmed with the user before proceeding, then investigated what actually happened instead of guessing.

### What actually happened, from the real backend logs
The user had uploaded a real 10,001-review CSV moments earlier. That triggered background RCA generation across 5+ clusters -- dozens of sequential NVIDIA calls in under a minute, during which NVIDIA's own API started returning `503 Service Unavailable`. The "Generate test" click landed right in the middle of that burst and queued behind it. The actual failure trace:

```
10:54:57  Retrying request to /chat/completions in 0.41s   <- OpenAI SDK's own internal retry
10:55:12  Retrying request to /chat/completions in 0.90s   <- (nested inside ours)
10:55:28  Retry 1/2 after 1s: Request timed out.           <- our own retry loop
10:55:30  HTTP 503 Service Unavailable
10:55:45  Retrying request to /chat/completions in 0.83s
10:56:01  generate() NVIDIA call failed: Request timed out. <- gave up after 64s
```

Two independent retry layers were stacking: `AsyncOpenAI`'s client-level retries (SDK default: 2) nested inside `_call_nvidia_api`'s own 2-attempt loop, each with a 15s timeout. Fixed by passing `max_retries=0` to the `AsyncOpenAI` client -- we already retry with backoff at our own layer; retrying at both layers only multiplies worst-case latency (up to ~64s observed) without adding real resilience, and makes failures far less predictable.

### The same log window also showed the RCA pipeline's own truncation bug, not yet fixed
```
RAGAS evaluation failed (non-fatal): The output is incomplete due to a max_tokens length limit.   (x4)
Structured finalize failed (... max_tokens length limit) -- using draft hypothesis as fallback
```
The exact same class of bug already fixed for `repro_stub_generator.py` (§16.3) -- the reasoning model spends a real token budget on hidden chain-of-thought before the actual structured output -- was still present in two call sites that were never touched during that earlier fix:
- `structured_rca.py`'s `generate_structured_rca`: `max_tokens=1800` (sized for the old 8B instruct model) → raised to `3000`.
- `evaluation.py`'s RAGAS `InstructorLLM`: was using **Instructor's own default of `max_tokens=1024`**, never explicitly configured at all → set via `model_args=InstructorModelArgs(max_tokens=3000)`.
- `evaluation.py`'s `_generate_score_reasoning`: `max_tokens=120` didn't truncate outright but cut an on-topic explanation off mid-sentence → raised to `350`.

### Verified
- `evaluate_rca()` re-run end to end: real Faithfulness/AnswerRelevancy scores returned with no truncation warning (previously failed on this exact class of call), and the reasoning explanation now ends on a complete sentence.
- `generate_structured_rca()` re-run directly: succeeded with a full 4-step reproduction list, no fallback-to-draft.
- A normal `llm.generate()` call still succeeds after the `max_retries=0` client change (confirms the fix didn't silently break the happy path) -- and, run at a deliberately tiny `max_tokens=20` as a sanity probe, reproduced the general form of the reasoning-leak issue completely independent of any single call site: the returned `content` was hidden-reasoning prose ("Okay, the user is asking me to say the word...") rather than the requested one-word answer, confirming this is a property of the configured model under tight budgets generally, not a bug specific to any one prompt.

---

## 20. Two more real bugs from actually reading generated output: a fabricated Playwright API, and a timeout too tight for its own fix (2026-08-27)

**Touched:** `backend/app/services/ai/repro_stub_generator.py`, `backend/app/services/llm_service.py`

The user tried the repro-stub generator again after §19's fixes, landed comfortably under the new ~30s ceiling, and pasted the actual generated code back for review instead of just reporting "it worked." Reading it (not just checking that it ran) surfaced two more real issues.

### 20.1 A fabricated Playwright API
The bug being tested was "app fails to load on mobile data (works over Wi-Fi)" -- reproducing it requires throttling network conditions, which the model handled by calling `context.setNetworkConditions({...})`. **This method does not exist on Playwright's `BrowserContext`.** Real network throttling in Playwright requires a CDP session (`context.newCDPSession(page)`, then `session.send('Network.emulateNetworkConditions', {...})`, Chromium-only) or isn't simulatable at all for some conditions (device GPS, real cellular radios). Run as-is, the generated test would fail with `TypeError: context.setNetworkConditions is not a function` on line 1, before ever reaching the assertion that mattered.

The existing guardrail ("never fabricate selectors, URLs, or test data... use TODO placeholders") only covered fabricated *content*, not fabricated *framework APIs* -- a gap, since a plausible-sounding-but-nonexistent method is the same category of dishonesty as a plausible-sounding-but-nonexistent selector. Added an explicit rule: stick to the well-documented Playwright core surface; for anything requiring a CDP session or a real device capability Playwright can't simulate, say so in a comment rather than inventing a clean-looking method.

**A self-inflicted bug while writing that fix**: the added guardrail text included literal `{...}` illustrating the CDP session call, and `_PROMPT_TEMPLATE` is a Python `.format()` string -- unescaped braces in the template broke every single call with `IndexError: Replacement index 0 out of range`. Caught immediately by re-running the exact prompt that had just produced the bad output, before it ever reached a real request. Fixed by rewording the guardrail without literal braces rather than escaping them, since the failure mode (an editor forgetting to double an added brace later) was worth removing structurally, not just patching once.

**Verified**: regenerated the exact cluster that had produced `setNetworkConditions` -- the corrected output now uses a real `newCDPSession` + `Network.emulateNetworkConditions` pattern, wrapped in a clean reusable helper function, with an added third test case (offline handling) still properly grounded in the RCA evidence.

### 20.2 The retry fix from §19 had exposed a second problem: 15s alone is too tight for a 3000-token call
Regenerating that same cluster to verify 20.1 failed three times in a row, consistently at ~31-33s -- not the flaky, load-dependent failures diagnosed in §19, but a systematic one. Root cause: `self.timeout = 15.0` was one fixed value for every call regardless of `max_tokens`, tuned against the old 8B instruct model. The current reasoning model routinely needs more than 15s per attempt once `max_tokens` is large enough to include real thinking room (repro stubs, structured RCA, RAGAS all use 3000). Before §19's `max_retries=0` fix, the SDK's own nested internal retries were incidentally providing extra attempts that sometimes got lucky within the 15s window; removing that nesting (correctly, for the reason in §19) also removed the accidental extra chances, so calls that were always borderline started failing every time instead of intermittently.

Fixed by scaling both knobs to the actual token budget instead of using one number for everything: `effective_timeout = 15s` for `max_tokens <= 800` (explain, playground, RAGAS reasoning -- unaffected, stay fast), else `max(15s, max_tokens / 60)` (3000 tokens -> 50s per attempt); and `max_retries` drops from 2 to 1 once `max_tokens > 800`, so a genuine outage on a large-budget call still fails in ~1x the scaled timeout instead of stacking back toward the multi-layer-retry problem §19 had just fixed.

**Verified**: the same cluster that failed 3/3 times succeeded in 24.5s immediately after the fix. A 5-cluster reliability sweep run back-to-back with zero spacing hit 2 immediate "Connection error" failures -- re-running those same two clusters in isolation (one call, no concurrent load) both succeeded in 36.7s and 41.3s, confirming the failures were an artifact of firing 5 large requests in a tight loop (not how a real user clicks a single "Generate test" button) rather than a regression from this fix.

---

## 21. §20's retry-count reduction was itself an over-correction; plus real output-format variance needed its own retry (2026-08-27)

**Touched:** `backend/app/services/llm_service.py`, `backend/app/services/ai/repro_stub_generator.py`

The very next real click after §20 shipped failed again -- a third distinct failure mode in three consecutive rounds, each one only visible by actually looking at what broke rather than assuming the previous fix covered it.

### 21.1 `max_retries=1` for large-budget calls removed real resilience
The actual error this time: `HTTP 503 - {"message": "Service temporarily overloaded"}` -- a genuine, if transient, condition on NVIDIA's side, not a timeout, not truncation, not the fabricated-API bug. §20 had dropped `max_retries` from 2 to 1 for calls with `max_tokens > 800`, reasoning that large calls already get a longer per-attempt timeout so retrying twice would stack worst-case latency back up. That reasoning conflated two different problems: the *nested*-retry issue from §19 (the SDK's own retries running inside ours, `max_retries=0` on the client already fixes that) has nothing to do with *how many attempts our own loop gets*. Cutting our own loop to 1 attempt meant a single transient 503 -- exactly the case retries exist for -- had zero chance to recover. Reverted to `max_retries = 2` for every call size; the scaled timeout from §20 was the fix that actually mattered.

### 21.2 The model doesn't format identically across samples, even at temperature=0.2
Re-running a reliability sweep to confirm 21.1 turned up a fourth thing: cluster 911 failed with "model response had no code block" -- the API call succeeded, but this particular sample's output didn't close its code fence the way every other sample that session had. Re-running the *identical* prompt moments later produced a cleanly fenced response. `llm.generate()`'s own retry logic only covers API/network-level failures; a successful-but-malformed response was invisible to it. Added a small retry loop inside `generate_test_stub` itself, scoped specifically to this failure mode (empty response, or no matching code fence) -- 2 attempts total, since a second consecutive miss is a much stronger signal something's actually wrong than one sample being unlucky.

### Verified
- Same cluster that had just failed with the 503 (1159) succeeded in 31.8s.
- Cluster 911 (the no-code-block failure) succeeded on the next attempt in 13.4s with the new retry loop in place.
- Full 5-cluster sweep, spaced 2s apart (not the zero-spacing that produced false "Connection error" positives in §20): **5/5 succeeded**, 14.3-42.9s range, zero fabricated APIs.
- Independently, the user pasted back a second real generated test (a different cluster, a network/offline bug) for review before this round even started: `page.context().setOffline(true/false)` -- confirmed as a genuine Playwright API (unlike §20's fabricated `setNetworkConditions`), correctly grounded in the actual review text, proper structure throughout. The §20 guardrail is generalizing correctly across different bug types, not just the one cluster it was fixed against.

---

## 22. Kanban board: real drag-and-drop persistence, and the type-mismatch bug that silently ate every drop (2026-08-27)

**Touched:** `frontend/src/components/ui/TicketCard.tsx`, `frontend/src/components/ui/KanbanBoard.tsx`, `frontend/src/app/(app)/dashboard/page.tsx`

§18 built the first real path to change a cluster's status (the checkmark button on the analytics page), but explicitly left the Kanban board itself unchanged — `KanbanBoard.tsx` rendered three columns with no drag-persist logic or API calls at all, a known, flagged limitation. This closes that gap: dragging a card between columns now actually calls the same `PATCH /clusters/{id}/status` endpoint from §18 and persists.

### New
- `TicketCard` takes a `draggable` prop; when set, the card is a real HTML5 drag source (`draggable`, `onDragStart` writing its id into `dataTransfer`).
- `KanbanColumn` becomes a real drop target when the board is given an `onStatusChange` handler: `onDragOver`/`onDrop` with a visual "drop here" state, and cards mid-save are dimmed (`opacity-40 pointer-events-none`) via a `movingId` prop so a second drag can't race the first.
- `dashboard/page.tsx`'s `handleStatusChange` does an optimistic move (updates local state immediately, before the network call), calls the real `PATCH` via `apiClient.updateClusterStatus`, and reverts the local state if the call fails — so the board never silently disagrees with the database on a failed save.

### A real bug found during live verification, not by the type-checker
First live drag test: the browser's own `left_click_drag` mouse simulation landed imprecisely (its target coordinates fell inside the *Fixing* column, not *Resolved*, once the actual rendered column boundaries were measured), which looked like nothing happened. Re-testing with a coordinate-accurate synthetic DOM drag (`dispatchEvent` of real `dragstart`/`dragover`/`drop` `DragEvent`s against the actual card and column elements) still produced **zero network calls** — a real bug, not a test-tooling artifact.

Root cause, found by walking the React fiber tree to inspect the actual prop values in memory: `Ticket.id` is typed as `string` in `KanbanBoard.tsx`, but the real data source (`cluster.id` from Supabase) is a **number**. `dataTransfer.setData()` coerces it to the string `"1165"` on the way out; `handleStatusChange`'s `tickets.find(t => t.id === ticketId)` then compares `1165 === "1165"` — always `false` under strict equality — so the handler's early-return guard (`if (!ticket) return`) silently swallowed every single drop before it ever reached the API call. No error, no console warning, no visual sign anything had gone wrong; the card would just not move.

Fixed at the source rather than patching the comparison: `dashboard/page.tsx` now maps `id: String(cluster.id)` when building tickets, so the id is a string everywhere downstream, matching what `dataTransfer` was always going to hand back on drop.

### Verified
Reproduced the exact failure with a coordinate-accurate synthetic drag (confirmed via React fiber inspection that `ticket.id` was `1165` as a `number`, not a string, before the fix — and confirmed zero `fetch`/PATCH calls fired on drop). After the fix, re-ran the identical synthetic drag against the same cluster (1165, `"too much bugs..."`, real production data) from Resolved → Fresh Roast: `PATCH /clusters/1165/status` fired and returned `{"id":1165,"status":"fresh_roast","resolved_at":null}`, the board's Fresh Roast/Resolved counts updated live (49→50, 1→0) with no page reload, matching the optimistic-then-confirmed update path. Dragged it back afterward to restore the original resolved state; confirmed via a second successful `PATCH` returning `status: "resolved"`.

---

## Summary — old vs. new, in one table

| Concern | Old | New |
|---|---|---|
| Embeddings | HF Inference API (network) by default | Local ONNX int8-quantized MiniLM by default |
| Similarity search | Always exact FAISS flat index | Exact below 100k reviews, HNSW approximate above |
| LLM provider | A4F → Groq cascading fallback, 9 models, 2 circuit breakers | One verified NVIDIA model, no circuit breakers |
| RCA generation | Single LLM call, free-text markdown | 5-node LangGraph agent: retrieve → hypothesize → critique → finalize (schema-validated) |
| RCA quality check | None | RAGAS Faithfulness + Answer Relevancy scoring |
| Precedent / memory | None | Hybrid (dense + BM25 + reranked) vector store of resolved clusters |
| Observability | None for LLM calls | Langfuse or local JSONL trace log, per-agent-step spans |
| Shadow v2 comparison | Ran on every upload (doubles processing time) | Disabled by default, env-gated sampling |
| DB credentials | Hardcoded fallback in source | Required env var, no fallback, fails loudly if missing |
| AI Debug Center | Static prompt copy tab | Live model-style/temperature playground |
| Debug Center trust signal | None | Clickable evidence citations, faithfulness badges |
| Upload failure handling | Could hang at "processing" forever | Explicitly marked `failed` with an error message |
| Upload progress bar | Bound to a field the backend never sent (animated to `undefined%`) | Size-aware estimate scaled by the file's real review count |
| Marketing hero | Phone-demo scroll animation | Scroll-driven "pipeline world" — 6 AI-generated scenes narrating the real backend pipeline |
| Regression detection | Keyword (Jaccard) title overlap only — blind to paraphrases | Keyword **+ semantic** embedding match, with confidence % and which signal caught it |
| Prioritisation | Severity alone; 4 independent signals shown as separate badges | Optional fused "⚡ Fix first" ranking (severity + AI faithfulness + regression + volume) |
| Notifications | None — no outbound webhook code existed at all | Slack/Discord alerts on fix-didn't-hold and new CRITICAL clusters |
| Repro steps | Terminal prose in the RCA | On-demand runnable Playwright test stub |
| Release correlation | `affected_versions` column existed but was never populated | Derived on read from per-review versions (10/51 real uploads have the data) |
| Cross-platform | Android/iOS versions of one bug triaged as two unrelated issues | Best-effort "same bug on both platforms?" candidate flagging |
| Kanban board | Rendered columns only — no drag persistence, no API calls | Real drag-and-drop, persists via `PATCH /clusters/{id}/status`, optimistic update with revert-on-failure |
