"""
RAGAS evaluation of generated RCA quality — this is what turns "we call an
LLM" into "we measure whether the LLM's output is actually grounded in the
evidence." Scores every RCA on:

  - Faithfulness: does the hypothesis only claim things supported by the
    actual user reviews (retrieved_contexts), or is it hallucinating?
  - Answer Relevancy: does the hypothesis actually address the reported
    issue (user_input), or does it wander off-topic?

Both scores are 0-1. Best-effort: evaluation failures never block RCA
generation — they're logged and the pipeline continues without a score.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

NVIDIA_API_URL = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

_faithfulness = None
_answer_relevancy = None


def _get_metrics():
    global _faithfulness, _answer_relevancy
    if _faithfulness is None or _answer_relevancy is None:
        import instructor
        from openai import AsyncOpenAI
        from ragas.llms import InstructorLLM
        from ragas.embeddings import HuggingFaceEmbeddings
        from ragas.metrics.collections import Faithfulness, AnswerRelevancy

        api_key = os.getenv("NVIDIA_API_KEY")
        raw_client = AsyncOpenAI(base_url=NVIDIA_API_URL, api_key=api_key)
        instructor_client = instructor.from_openai(raw_client, mode=instructor.Mode.TOOLS)

        ragas_llm = InstructorLLM(client=instructor_client, model=NVIDIA_MODEL, provider="openai")
        ragas_embeddings = HuggingFaceEmbeddings(
            model="sentence-transformers/all-MiniLM-L6-v2", device="cpu"
        )

        _faithfulness = Faithfulness(llm=ragas_llm)
        _answer_relevancy = AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embeddings)
        logger.info("✅ RAGAS evaluators initialized (NVIDIA LLM + local embeddings)")

    return _faithfulness, _answer_relevancy


async def _generate_score_reasoning(
    issue_title: str,
    hypothesis_text: str,
    review_contexts: list[str],
    faithfulness: float,
    answer_relevancy: float,
) -> Optional[str]:
    """
    RAGAS gives a number, not a "why" — this asks the same LLM for a short,
    concrete justification tied to THIS cluster's actual hypothesis and
    evidence, e.g. "Faithfulness is low because the hypothesis blames a
    specific SDK that no review mentions." One extra call, kept short.
    """
    try:
        from app.services.llm_service import FALLBACK_MESSAGE, get_llm_service

        evidence = "\n".join(f'- "{c}"' for c in review_contexts[:5])
        prompt = f"""In 1-2 short sentences, explain WHY this RCA hypothesis scored
faithfulness={faithfulness:.2f} and answer_relevancy={answer_relevancy:.2f} (both 0-1,
higher is better). Be concrete: point at specific claims in the hypothesis that are
or aren't backed by the reviews. No preamble, just the explanation.

Issue: {issue_title}

Hypothesis:
{hypothesis_text}

Review evidence:
{evidence}"""

        llm = get_llm_service()
        reasoning = await llm.generate(prompt, max_tokens=120)
        if reasoning == FALLBACK_MESSAGE:
            # generate() never raises on failure -- it returns this sentinel
            # instead. Without this check it gets stored and shown to the
            # user as if it were real model output.
            return None
        return reasoning.strip()
    except Exception as e:
        logger.warning(f"⚠️  Score reasoning generation failed (non-fatal): {e}")
        return None


async def evaluate_rca(
    issue_title: str, hypothesis_text: str, review_contexts: list[str]
) -> Optional[dict]:
    """
    Scores a generated RCA hypothesis against the review evidence it was
    built from, plus a short natural-language justification for the scores.
    Returns None (never raises) if evaluation itself fails — a failed eval
    shouldn't take down RCA generation.
    """
    if not hypothesis_text or not review_contexts:
        return None

    try:
        faithfulness, answer_relevancy = _get_metrics()

        faithfulness_result = await faithfulness.ascore(
            user_input=issue_title,
            response=hypothesis_text,
            retrieved_contexts=review_contexts,
        )
        relevancy_result = await answer_relevancy.ascore(
            user_input=issue_title,
            response=hypothesis_text,
        )

        faithfulness_score = round(float(faithfulness_result.value), 3)
        relevancy_score = round(float(relevancy_result.value), 3)

        reasoning = await _generate_score_reasoning(
            issue_title, hypothesis_text, review_contexts, faithfulness_score, relevancy_score
        )

        return {
            "faithfulness": faithfulness_score,
            "answer_relevancy": relevancy_score,
            "reasoning": reasoning,
        }
    except Exception as e:
        logger.warning(f"⚠️  RAGAS evaluation failed (non-fatal): {e}")
        return None
