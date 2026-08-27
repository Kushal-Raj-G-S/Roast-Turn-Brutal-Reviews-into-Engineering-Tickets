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

import asyncio
import logging
import re

from app.services.llm_service import get_llm_service, FALLBACK_MESSAGE
from app.models.bulk_models import Cluster

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```(?:typescript|ts)?\s*\n(.*?)```", re.DOTALL)


_PROMPT_TEMPLATE = """You write realistic, well-structured Playwright test files from a bug report. Junior engineers will read and extend this, so it needs to actually look like a real test file, not a one-line stub.

Bug: {title}
Severity: {severity}

Root cause / reproduction steps (from an internal RCA):
{steps}

Suggested fix (if any):
{fix}

Real user reviews describing this bug (use these for concrete detail -- exact wording, what action they were doing, what they expected):
{evidence}

Write ONE Playwright test file (TypeScript) for this bug. Structure it properly:
- A `test.describe()` block named after the bug.
- A `test.beforeEach()` that does shared setup (e.g. navigation) if the repro steps imply repeated setup -- don't invent one if there's nothing to share.
- Break the repro steps into SEPARATE, individually-commented actions (locate -> act -> assert), not one giant unexplained block. Each action's comment should reference what specifically justifies it (a step from the RCA, or a phrase from a review) -- e.g. `// review: "crashes every time I upload a photo" -> attach a file, expect no crash`.
- The main test should FAIL until the bug is fixed -- mark it clearly (`// EXPECTED TO FAIL UNTIL FIXED`) and assert the behavior that SHOULD be true once it's fixed, not the broken behavior.
- If the evidence supports it, add one additional focused test for an edge case or a related assertion (e.g. an error boundary, a specific error message) -- only if it's actually grounded in the evidence, not filler.
- Never fabricate selectors, URLs, or test data that aren't implied by the bug report -- use clearly-marked TODO placeholders (e.g. `'TODO: selector for upload button'`) instead of inventing plausible-looking but fake ones. A TODO is honest; a fake selector is not.
- Only use Playwright APIs that actually exist. Stick to the well-known core surface: page.goto, page.locator, .click()/.fill()/.setInputFiles(), expect(locator).toBeVisible()/.toHaveText()/.toContainText(), page.route() for mocking network responses, test.describe/beforeEach/fail. If the bug genuinely needs something outside that (e.g. throttling network speed, GPS/geolocation, device orientation) -- these are NOT plain context/page methods in Playwright, they need a CDP session (context.newCDPSession(page), then session.send with 'Network.emulateNetworkConditions' and the relevant options, Chromium-only) or a real device/OS capability Playwright can't simulate at all. In that case say so directly in a comment (e.g. "TODO: this requires a CDP session for network throttling -- see Playwright's CDPSession docs") rather than inventing a clean-looking method that doesn't exist. A test that fails with "no such API" on line 1 is worse than a TODO -- it wastes an engineer's time before they even find the assertion that matters.
- Roughly 40-70 lines -- enough to be a real test file, not padded.
- Output ONLY the code, in a single ```typescript fenced block, no prose before or after.
"""


async def generate_test_stub(cluster: Cluster) -> str:
    """Returns a fenced TypeScript code block. Raises on total LLM failure."""
    steps = cluster.rca_steps or "(no structured repro steps recorded -- infer minimally from the title only)"
    fix = cluster.rca_fix or "(none recorded)"

    reviews = (cluster.sample_reviews or [])[:3]
    if reviews:
        evidence = "\n".join(f'- "{r.get("content", "").strip()[:200]}"' for r in reviews if r.get("content"))
    else:
        evidence = "(no sample review text recorded -- rely on the title and repro steps only)"

    prompt = _PROMPT_TEMPLATE.format(
        title=cluster.title,
        severity=cluster.severity,
        steps=steps,
        fix=fix,
        evidence=evidence or "(no sample review text recorded)",
    )

    llm = get_llm_service()
    # The configured model is a reasoning model that spends a real chunk of
    # its token budget on hidden chain-of-thought before ever writing code
    # (see the code-fence extraction below) -- 1400 was measured truncating
    # mid-file with no closing fence on a moderately detailed cluster. 3000
    # leaves enough room for both the reasoning and a complete ~40-70 line
    # test file.
    #
    # One retry specifically for "the API call succeeded but the response
    # had no valid code fence" -- llm.generate() already retries on its own
    # for network/server errors (timeouts, 503s), but a malformed-yet-
    # successful response is a different failure mode it can't see, and
    # this model doesn't format the same way on every sample even at
    # temperature=0.2 (observed: identical prompt, one run fenced cleanly,
    # the next didn't). Only 1 extra attempt -- if it fails twice in a row
    # that's a stronger signal something's actually wrong, not just noise.
    #
    # A short backoff before that retry, not just an immediate re-call:
    # generate() also swallows total failure (a transient 503 burst that
    # outlasts its own internal 2-attempt/backoff window) and returns
    # FALLBACK_MESSAGE rather than raising -- retrying that instantly just
    # re-hits the same overload window NVIDIA was still in. _call_nvidia_api
    # already backs off between ITS attempts; this loop was the one layer
    # that didn't, despite wrapping the same class of transient failure.
    last_error = None
    for attempt in range(2):
        if attempt > 0:
            logger.info(f"Retrying test stub generation after backoff -- previous attempt failed: {last_error}")
            await asyncio.sleep(2)

        result = await llm.generate(prompt, max_tokens=3000, temperature=0.2)

        if result == FALLBACK_MESSAGE or not result.strip():
            last_error = "LLM call did not return usable output"
            continue

        # The configured model (a reasoning model) ignores "output only
        # code, no prose" instructions in practice -- it reliably prepends
        # its full chain-of-thought before the fenced code block regardless
        # of prompting. Extract just the code rather than trust the
        # instruction was followed; returning the raw response would dump
        # several KB of reasoning prose into what's supposed to be a code
        # box in the UI.
        match = _CODE_FENCE.search(result)
        if not match:
            last_error = "model response had no code block"
            continue

        return match.group(1).strip()

    raise RuntimeError(f"Test stub generation failed after retry ({last_error})")
