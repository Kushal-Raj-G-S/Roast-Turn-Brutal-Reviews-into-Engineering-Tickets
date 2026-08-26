"""
Repro test stub generator.

Closes review -> ticket -> *runnable test* instead of stopping at prose: takes
whatever repro steps already exist for a cluster (rca_steps, written by the
RCA agent pipeline) and asks the same LLM used everywhere else in the product
to turn them into an actual Playwright test skeleton. No new model, no new
API, no new cost beyond one extra generate() call -- reuses the singleton
LLMService so it shares the same self-throttled rate limit as every other
caller (see llm_service.py).

Best-effort like the rest of the AI layer: on any failure this raises, and
the route handler is expected to surface that as a normal HTTP error rather
than silently returning something misleading (unlike RCA generation, there's
no safe "fallback text" for a test stub -- a wrong one is worse than none).
"""

from app.services.llm_service import get_llm_service, FALLBACK_MESSAGE
from app.models.bulk_models import Cluster


_PROMPT_TEMPLATE = """You write minimal, runnable Playwright test skeletons from a bug report.

Bug: {title}
Severity: {severity}

Root cause / reproduction steps (from an internal RCA):
{steps}

Suggested fix (if any):
{fix}

Write ONE Playwright test file (TypeScript) that reproduces this bug as a failing test an engineer can run today. Rules:
- Use `test.fail()` or a comment marking it EXPECTED TO FAIL UNTIL FIXED if the assertion encodes the bug not yet being fixed -- don't fabricate selectors or URLs that weren't implied by the bug report; use clearly-marked TODO placeholders (e.g. `'TODO: selector for login button'`) instead of inventing plausible-looking but fake ones.
- Keep it under 40 lines.
- Output ONLY the code, in a single ```typescript fenced block, no prose before or after.
"""


async def generate_test_stub(cluster: Cluster) -> str:
    """Returns a fenced TypeScript code block. Raises on total LLM failure."""
    steps = cluster.rca_steps or "(no structured repro steps recorded -- infer minimally from the title only)"
    fix = cluster.rca_fix or "(none recorded)"

    prompt = _PROMPT_TEMPLATE.format(
        title=cluster.title,
        severity=cluster.severity,
        steps=steps,
        fix=fix,
    )

    llm = get_llm_service()
    result = await llm.generate(prompt, max_tokens=700, temperature=0.2)

    if result == FALLBACK_MESSAGE or not result.strip():
        raise RuntimeError("Test stub generation failed (LLM call did not return usable output)")

    return result.strip()
