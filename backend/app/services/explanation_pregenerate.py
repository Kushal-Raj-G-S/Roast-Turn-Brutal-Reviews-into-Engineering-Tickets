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
from datetime import datetime

from sqlmodel import Session, select

from app.models.bulk_models import Cluster, SeverityExplanation
from app.services.llm_service import LLMService
from app.services import explanation_cache

logger = logging.getLogger(__name__)

SEVERITIES = ["critical", "high", "medium", "low"]
MAX_CLUSTERS_PER_SEV = 10   # Top N clusters (by review_count) fed to LLM
MAX_REVIEWS_PER_CLUSTER = 5  # Sample reviews per cluster in prompt


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
