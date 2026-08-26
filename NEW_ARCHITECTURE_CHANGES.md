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
