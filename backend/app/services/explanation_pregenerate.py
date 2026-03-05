"""
Pre-generates one AI explanation per severity category (critical/high/medium/low)
immediately after a bulk processing job completes.

Strategy:
- Reads all clusters for the upload, groups by severity
- For each severity group: pulls top-N clusters by review_count
- Sends up to 5 sample reviews per cluster to the LLM
- Produces a concise category summary (≤300 words)
- Persists to severity_explanations DB table (survives restarts)
- Also caches in-memory for O(1) hot reads within the same process

Total LLM calls: 4 parallel requests (one per severity that has clusters)
Total time: ~60-90s (limited by slowest LLM call, not sum of all 4)
"""

import asyncio
import logging
import re
import os
from datetime import datetime

from sqlmodel import Session, select

from app.models.bulk_models import Cluster, SeverityExplanation, Upload
from app.services.llm_service import LLMService
from app.services import explanation_cache

logger = logging.getLogger(__name__)

SEVERITIES = ["critical", "high", "medium", "low"]
MAX_CLUSTERS_PER_SEV = 10   # Top N clusters (by review_count) fed to LLM
MAX_REVIEWS_PER_CLUSTER = 5  # Sample reviews per cluster in prompt
MAX_CLUSTERS_FOR_RCA = 5    # Top CRITICAL+HIGH clusters for full 7-section RCA
MAX_TOKENS_RCA = 2000       # Per-cluster RCA needs more space than category summaries


def _clean_title(title: str) -> str:
    import re
    return re.sub(r'^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*(Issue:\s*)?', '', title, flags=re.IGNORECASE).strip()


def _build_prompt(severity: str, clusters: list[Cluster]) -> str:
    sections = []
    for idx, c in enumerate(clusters, 1):
        title = _clean_title(c.title)
        reviews = (c.sample_reviews or [])[:MAX_REVIEWS_PER_CLUSTER]
        review_lines = "\n".join(
            f'    - ({r.get("rating", "?")}★) "{r.get("content", "").strip()[:130]}"'
            for r in reviews
        )
        sections.append(
            f'{idx}. **{title}** ({c.review_count} users)\n{review_lines}'
        )

    cluster_block = "\n\n".join(sections)

    return f"""You are analysing {severity.upper()} severity issues from a batch of app reviews.

Below are the top {len(clusters)} issue cluster(s) at this severity level, each with sample user reviews:

{cluster_block}

Write a clear, honest CATEGORY SUMMARY covering all {severity.upper()} issues above.
Structure your response EXACTLY as:

**Overview**
2-3 sentences: What is the overall theme of {severity} issues? What pain are users commonly feeling?

**Top Issues**
Bullet list (one line each): most impactful problem titles with the count of affected users.

**Common Thread**
1-2 sentences: What connects these issues — a specific feature area, platform, or user action?

**Action Required**
1-2 sentences for the development team: what should be prioritised for {severity} severity?

Rules:
- Every claim must be backed by the reviews listed above
- Be direct and specific — no corporate filler
- If severity label seems wrong for any cluster, note it briefly
- Keep total response under 300 words"""


async def _generate_one_severity(
    upload_id: int,
    severity: str,
    clusters: list[Cluster],
    llm: LLMService,
    engine,
) -> None:
    """Generate explanation for one severity level."""
    logger.info(f"[pregenerate/{severity}] Task started for upload {upload_id}")
    
    empty_text = f"No {severity} severity issues were found in this upload."

    if not clusters:
        _upsert_db(engine, upload_id, severity, "done", empty_text)
        explanation_cache.set_explanation(upload_id, severity, empty_text)
        logger.info(f"[pregenerate/{severity}] Skipped (no clusters) for upload {upload_id}")
        return

    explanation_cache.set_status(upload_id, severity, "generating")
    _upsert_db(engine, upload_id, severity, "generating", None)
    logger.info(f"[pregenerate/{severity}] Generating explanation ({len(clusters)} clusters) for upload {upload_id}")

    try:
        prompt = _build_prompt(severity, clusters)
        explanation = await llm.generate(prompt, max_tokens=650)
        text = explanation.strip()
        _upsert_db(engine, upload_id, severity, "done", text)
        explanation_cache.set_explanation(upload_id, severity, text)
        logger.info(f"[pregenerate/{severity}] ✓ Done for upload {upload_id}")
    except Exception as e:
        logger.error(f"[pregenerate/{severity}] Failed for upload {upload_id}: {e}")
        _upsert_db(engine, upload_id, severity, "failed", None)
        explanation_cache.set_status(upload_id, severity, "failed")


async def pregenerate_for_upload(upload_id: int, engine) -> None:
    """
    Fire-and-forget task: generates 4 category explanations in PARALLEL.
    Called automatically after processing completes.
    Total time: ~1-2 min (limited by slowest LLM call, not sum of all 4).
    """
    logger.info(f"[pregenerate] Starting 4-category PARALLEL explanation for upload {upload_id}")

    # --- Load clusters ---
    try:
        with Session(engine) as session:
            all_clusters: list[Cluster] = session.exec(
                select(Cluster).where(Cluster.upload_id == upload_id)
            ).all()
    except Exception as e:
        logger.error(f"[pregenerate] DB read failed for upload {upload_id}: {e}")
        for sev in SEVERITIES:
            explanation_cache.set_status(upload_id, sev, "failed")
        return

    # Group + sort by review_count desc, cap at MAX_CLUSTERS_PER_SEV
    grouped: dict[str, list[Cluster]] = {s: [] for s in SEVERITIES}
    for c in all_clusters:
        if c.severity in grouped:
            grouped[c.severity].append(c)
    for sev in SEVERITIES:
        grouped[sev] = sorted(grouped[sev], key=lambda c: c.review_count, reverse=True)[:MAX_CLUSTERS_PER_SEV]

    # --- Generate all 4 severities in PARALLEL ---
    llm = LLMService()
    logger.info(f"[pregenerate] Generating 4 severities in parallel for upload {upload_id}")
    
    # Create coroutines (not tasks) and pass directly to gather
    coroutines = [
        _generate_one_severity(upload_id, sev, grouped[sev], llm, engine)
        for sev in SEVERITIES
    ]
    
    # gather() will schedule them all concurrently
    results = await asyncio.gather(*coroutines, return_exceptions=True)
    
    # Log any exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[pregenerate] {SEVERITIES[i]} failed: {result}")

    logger.info(f"[pregenerate] ✅ All 4 severities completed for upload {upload_id}")

    # Also trigger per-cluster structured RCA for critical/high clusters
    try:
        await pregenerate_rca_for_clusters(upload_id, engine)
    except Exception as rca_err:
        logger.warning(f"[pregenerate] Per-cluster RCA trigger failed (non-fatal): {rca_err}")


def _upsert_db(engine, upload_id: int, severity: str, status: str, explanation: str | None) -> None:
    """Insert or update a SeverityExplanation row."""
    try:
        with Session(engine) as session:
            row = session.exec(
                select(SeverityExplanation).where(
                    SeverityExplanation.upload_id == upload_id,
                    SeverityExplanation.severity == severity,
                )
            ).first()

            if row:
                row.status = status
                if explanation is not None:
                    row.explanation = explanation
                    row.generated_at = datetime.utcnow()
            else:
                row = SeverityExplanation(
                    upload_id=upload_id,
                    severity=severity,
                    status=status,
                    explanation=explanation,
                    generated_at=datetime.utcnow() if explanation else None,
                )
                session.add(row)

            session.commit()
    except Exception as e:
        logger.warning(f"[pregenerate] DB upsert failed ({severity}): {e}")


# ---------------------------------------------------------------------------
# Per-cluster structured RCA (7-section template)
# ---------------------------------------------------------------------------

def _extract_app_name(filename: str) -> str:
    """Derive a readable app name from the upload filename."""
    name = os.path.splitext(filename)[0]          # strip extension
    name = re.sub(r"[_\-]+", " ", name)           # underscores / hyphens → spaces
    name = re.sub(r"\s+", " ", name).strip().title()
    return name or "Unknown App"


def _detect_platform(cluster: Cluster) -> str:
    """Best-effort platform detection from cluster title and keywords."""
    text = ((cluster.title or "") + " " + " ".join(cluster.keywords or [])).lower()
    has_android = bool(re.search(r"\bandroid\b|\bplay.?store\b", text))
    has_ios = bool(re.search(r"\bios\b|\biphone\b|\bipad\b|\bapp.?store\b", text))
    if has_android and has_ios:
        return "both"
    if has_android:
        return "android"
    if has_ios:
        return "ios"
    return "unknown"


def _build_rca_prompt(cluster: Cluster, app_name: str) -> str:
    """
    Build a per-cluster RCA prompt following the structured 7-section template
    (RCA_template.md).  Feeds up to MAX_REVIEWS_PER_CLUSTER sample reviews as
    numbered evidence entries.
    """
    title = _clean_title(cluster.title)
    severity = cluster.severity.upper()
    platform = _detect_platform(cluster)
    cluster_size = str(cluster.review_count)

    reviews = (cluster.sample_reviews or [])[:MAX_REVIEWS_PER_CLUSTER]
    if reviews:
        parts = []
        for i, r in enumerate(reviews, 1):
            rating = r.get("rating", "?")
            content = r.get("content", "").strip()[:200]
            parts.append(f'[{i}] Rating: {rating}\u2605\n"{content}"')
        review_entries = "\n\n".join(parts)
    else:
        review_entries = "No sample reviews available."

    return f"""You are a senior mobile / full-stack engineer performing root cause analysis (RCA) on production issues surfaced from app store reviews.

Use ONLY the evidence provided below.

Rules:
* Ground every claim in the user reviews.
* Do NOT invent specific modules, services, or SDKs unless clearly implied.
* If information is missing write exactly: **"Unknown \u2013 need more data"** and explain what data would resolve it.
* Do NOT leave any section empty.
* Always include a **severity_assessment**, even if it matches the reported severity.
* If the feature/flow involves ads or performance, assume client-side scope unless evidence indicates backend.

---

INCIDENT CONTEXT

App: {app_name}
Platform: {platform}
Feature / Flow: {title}
Reported Severity: {severity}
Cluster Size: {cluster_size}
Data Source: App store reviews (clustered by semantic similarity)

---

EVIDENCE \u2014 USER REVIEWS

{review_entries}

---

REQUIRED RCA OUTPUT

### 1. Root Cause Hypothesis

* likelihood: {{high | medium | low}}
* scope: {{functional | performance | UX | monetization | stability | unknown}}
* explanation: 2\u20134 sentences referencing review IDs.
* severity_assessment:
  * input: {severity}
  * suggested: {{CRITICAL | HIGH | MEDIUM | LOW}}
  * reason: 1\u20132 sentences.

---

### 2. Affected Surface Area

* client_ui:
* client_logic (view models / controllers / state):
* network_api (endpoints, request/response handling):
* backend_service (API / microservice / DB behavior):
* config_experiments (feature flags / A/B tests / remote config):

---

### 3. Reproduction Steps

Provide a minimal reproducible scenario. Mark assumptions explicitly.

1.
2.
3.

---

### 4. Diagnostic Checklist

* client_logs:
* backend_logs:
* metrics:
* flags_experiments:
* other_tools (crash analytics, tracing, etc.):

---

### 5. Recommended Fix

* summary:
* implementation_notes:
  * actionable fix suggestion
  * fallback fix or mitigation

---

### 6. Prevention

* tests:
* monitoring_process:

---

### 7. Notes

* uncertainties:
* additional_data_needed:"""


async def _generate_rca_for_one_cluster(
    cluster_id: int,
    app_name: str,
    llm: LLMService,
    engine,
) -> None:
    """Generate and persist a structured RCA for a single cluster."""
    try:
        with Session(engine) as session:
            cluster = session.get(Cluster, cluster_id)
            if not cluster:
                logger.warning(f"[rca] Cluster {cluster_id} not found — skipping")
                return

        prompt = _build_rca_prompt(cluster, app_name)
        logger.info(
            f"[rca] Generating RCA for cluster {cluster_id} "
            f"({cluster.title[:60]}\u2026 | {cluster.review_count} reviews)"
        )

        rca_text = await llm.generate(prompt, max_tokens=MAX_TOKENS_RCA)
        rca_text = rca_text.strip()

        with Session(engine) as session:
            cluster = session.get(Cluster, cluster_id)
            if cluster:
                cluster.rca_hypothesis = rca_text
                cluster.ai_analyzed = True
                cluster.updated_at = datetime.utcnow()
                session.add(cluster)
                session.commit()
                logger.info(f"[rca] \u2713 Persisted RCA for cluster {cluster_id}")

    except Exception as e:
        logger.error(f"[rca] Failed for cluster {cluster_id}: {e}")


async def pregenerate_rca_for_clusters(upload_id: int, engine) -> None:
    """
    Generate structured 7-section RCA reports for the top CRITICAL + HIGH
    clusters in a completed upload.

    * Skips clusters that already have rca_hypothesis set.
    * Runs up to MAX_CLUSTERS_FOR_RCA calls in parallel via asyncio.gather.
    * Stores each result in cluster.rca_hypothesis + marks ai_analyzed = True.
    """
    logger.info(f"[rca] Starting per-cluster RCA for upload {upload_id}")

    try:
        with Session(engine) as session:
            upload = session.get(Upload, upload_id)
            if not upload:
                logger.error(f"[rca] Upload {upload_id} not found \u2014 aborting")
                return
            app_name = _extract_app_name(upload.filename)

            candidates: list[Cluster] = session.exec(
                select(Cluster)
                .where(
                    Cluster.upload_id == upload_id,
                    Cluster.severity.in_(["critical", "high"]),
                    (Cluster.ai_analyzed.is_(None)) | (Cluster.ai_analyzed == False),  # noqa: E712
                )
                .order_by(Cluster.review_count.desc())
            ).all()

    except Exception as e:
        logger.error(f"[rca] DB read failed for upload {upload_id}: {e}")
        return

    if not candidates:
        logger.info(f"[rca] No eligible clusters for upload {upload_id} (all already analyzed or none exist)")
        return

    targets = candidates[:MAX_CLUSTERS_FOR_RCA]
    logger.info(
        f"[rca] Processing {len(targets)} cluster(s) for upload {upload_id} (app: {app_name})"
    )

    llm = LLMService()
    tasks = [
        _generate_rca_for_one_cluster(c.id, app_name, llm, engine)
        for c in targets
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[rca] Cluster {targets[i].id} RCA failed: {result}")

    logger.info(f"[rca] \u2705 Per-cluster RCA complete for upload {upload_id}")
