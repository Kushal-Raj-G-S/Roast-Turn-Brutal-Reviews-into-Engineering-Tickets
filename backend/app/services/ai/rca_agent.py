"""
Agentic RCA pipeline — LangGraph state machine with real tool use, instead
of a single LLM completion.

    investigate → retrieve_similar (hybrid-search tool) → hypothesize
        → critique → finalize (structured output)

Each node is traced (Langfuse or local JSONL). `retrieve_similar` is a real
tool call into the Qdrant/BM25/reranker hybrid search stack, so the model's
hypothesis is grounded not just in this upload's reviews but in the
project's accumulated memory of previously resolved issues.
"""

import logging
from typing import Any, Optional, TypedDict

from app.services.ai import vector_store
from app.services.ai.observability import Trace, start_trace
from app.services.ai.structured_rca import StructuredRCA, generate_structured_rca
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)


class RCAState(TypedDict, total=False):
    cluster_id: Optional[int]
    title: str
    severity: str
    app_name: str
    platform: str
    reviews: list[dict[str, Any]]
    keywords: list[str]

    evidence_text: str
    similar_issues: list[vector_store.SimilarIssue]
    hypothesis_draft: str
    critique: str
    final_rca: Optional[StructuredRCA]

    trace: Any  # observability.Trace — not graph state we need serialized


def _format_reviews(reviews: list[dict[str, Any]], limit: int = 5) -> str:
    parts = []
    for i, r in enumerate(reviews[:limit], 1):
        rating = r.get("rating", "?")
        content = (r.get("content") or "").strip()[:220]
        parts.append(f'[{i}] {rating}★ "{content}"')
    return "\n".join(parts) if parts else "No sample reviews available."


async def _node_investigate(state: RCAState) -> RCAState:
    trace: Trace = state["trace"]
    with trace.span("investigate", input_data=state.get("title")) as span:
        evidence = _format_reviews(state.get("reviews", []))
        span["output"] = f"{len(state.get('reviews', []))} reviews summarized"
    return {**state, "evidence_text": evidence}


async def _node_retrieve_similar(state: RCAState) -> RCAState:
    """Tool call: hybrid-search the vector store for precedent."""
    trace: Trace = state["trace"]
    with trace.span("retrieve_similar_tool", input_data=state.get("title")) as span:
        similar = vector_store.hybrid_search(
            query=state.get("title", ""),
            top_k=3,
            exclude_cluster_id=state.get("cluster_id"),
        )
        span["output"] = f"found {len(similar)} similar past issue(s)"
    return {**state, "similar_issues": similar}


def _similar_issues_block(similar: list[vector_store.SimilarIssue]) -> str:
    if not similar:
        return "None found — this appears to be a new issue category."
    lines = []
    for s in similar:
        resolution = s.rca_fix or "no recorded fix"
        lines.append(f'- "{s.title}" ({s.severity}, {s.status}) — resolution: {resolution}')
    return "\n".join(lines)


async def _node_hypothesize(state: RCAState) -> RCAState:
    trace: Trace = state["trace"]
    llm = get_llm_service()

    prompt = f"""Analyze this issue cluster and draft an initial root-cause hypothesis.

App: {state.get('app_name')}
Platform: {state.get('platform')}
Issue: {state.get('title')}
Severity: {state.get('severity')}

User review evidence:
{state['evidence_text']}

Similar past issues (from project history — may or may not be related):
{_similar_issues_block(state.get('similar_issues', []))}

Draft a concise (3-5 sentence) initial hypothesis for the root cause. If a similar
past issue looks like a regression of the same root cause, say so explicitly."""

    with trace.span("hypothesize", input_data=prompt) as span:
        draft = await llm.generate(prompt, max_tokens=400)
        span["output"] = draft

    return {**state, "hypothesis_draft": draft}


async def _node_critique(state: RCAState) -> RCAState:
    trace: Trace = state["trace"]
    llm = get_llm_service()

    prompt = f"""You are reviewing a colleague's draft root-cause hypothesis before it ships to engineering.

Issue: {state.get('title')}
Evidence:
{state['evidence_text']}

Draft hypothesis:
{state['hypothesis_draft']}

Critique this draft in 2-4 sentences: what's unsupported by the evidence, what's
missing, or what alternative explanation was overlooked? If the draft is solid,
say so and note only minor gaps."""

    with trace.span("critique", input_data=prompt) as span:
        critique = await llm.generate(prompt, max_tokens=300)
        span["output"] = critique

    return {**state, "critique": critique}


def _final_prompt(state: RCAState) -> str:
    return f"""Produce the FINAL structured root cause analysis, incorporating the
draft hypothesis, the critique of that draft, and the raw evidence below. Resolve
any gaps the critique raised where possible; otherwise note them in `notes`.

App: {state.get('app_name')}
Platform: {state.get('platform')}
Issue: {state.get('title')}
Reported severity: {state.get('severity')}

User review evidence:
{state['evidence_text']}

Similar past issues:
{_similar_issues_block(state.get('similar_issues', []))}

Draft hypothesis:
{state['hypothesis_draft']}

Critique of draft:
{state['critique']}"""


async def _node_finalize(state: RCAState) -> RCAState:
    trace: Trace = state["trace"]
    prompt = _final_prompt(state)

    with trace.span("finalize_structured", input_data=prompt) as span:
        try:
            final = await generate_structured_rca(prompt)
            span["output"] = final.model_dump()
        except Exception as e:
            logger.warning(f"⚠️  Structured finalize failed ({e}) — using draft hypothesis as fallback")
            span["output"] = f"FAILED: {e}"
            final = None

    return {**state, "final_rca": final}


_compiled_graph = None


def _build_graph():
    global _compiled_graph
    if _compiled_graph is None:
        from langgraph.graph import StateGraph, END

        graph = StateGraph(RCAState)
        graph.add_node("investigate", _node_investigate)
        graph.add_node("retrieve_similar", _node_retrieve_similar)
        graph.add_node("hypothesize", _node_hypothesize)
        graph.add_node("critique", _node_critique)
        graph.add_node("finalize", _node_finalize)

        graph.set_entry_point("investigate")
        graph.add_edge("investigate", "retrieve_similar")
        graph.add_edge("retrieve_similar", "hypothesize")
        graph.add_edge("hypothesize", "critique")
        graph.add_edge("critique", "finalize")
        graph.add_edge("finalize", END)

        _compiled_graph = graph.compile()
        logger.info("✅ RCA agent graph compiled")
    return _compiled_graph


async def run_rca_agent(
    cluster_id: Optional[int],
    title: str,
    severity: str,
    app_name: str,
    platform: str,
    reviews: list[dict[str, Any]],
    keywords: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Runs the full agentic RCA pipeline for one cluster.

    Returns a dict with:
      - final_rca: StructuredRCA | None (None if the model failed to produce
        a valid structured output after retries — very rare)
      - hypothesis_draft / critique: the intermediate reasoning, for transparency
      - similar_issues: precedent found via hybrid search
      - trace_id: id of the observability trace (Langfuse or local JSONL)
    """
    graph = _build_graph()
    trace = start_trace("rca_agent", metadata={"cluster_id": cluster_id, "title": title, "severity": severity})

    initial_state: RCAState = {
        "cluster_id": cluster_id,
        "title": title,
        "severity": severity,
        "app_name": app_name,
        "platform": platform,
        "reviews": reviews,
        "keywords": keywords or [],
        "trace": trace,
    }

    result = await graph.ainvoke(initial_state)

    trace_id = trace.finish(output={
        "final_rca": result["final_rca"].model_dump() if result.get("final_rca") else None,
        "similar_issues_found": len(result.get("similar_issues", [])),
    })

    return {
        "final_rca": result.get("final_rca"),
        "hypothesis_draft": result.get("hypothesis_draft"),
        "critique": result.get("critique"),
        "similar_issues": result.get("similar_issues", []),
        "trace_id": trace_id,
    }
