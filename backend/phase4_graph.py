"""LangGraph orchestration for the existing KnowledgePilot RAG flow."""

import logging
import re
from collections.abc import Callable
from inspect import signature
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.mcp_tools import build_document_server, call_document_search
from llm_service import LLMServiceError, generate_answer

logger = logging.getLogger(__name__)


def _record(trace: list[dict[str, Any]], step: str, status: str, started: float) -> None:
    event = {"step": step, "status": status, "duration_ms": round((perf_counter() - started) * 1000, 2)}
    trace.append(event)
    logger.info("phase4_trace step=%s status=%s duration_ms=%.2f", step, status, event["duration_ms"])


class QuestionState(TypedDict, total=False):
    documents: list[dict[str, Any]]
    question: str
    search_question: str
    course_id: str
    user_id: str
    page: int | None
    history: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    passages: list[dict[str, Any]]
    answer: str
    mode: str
    error: str | None
    mcp_used: bool
    fallback_used: bool


def build_question_graph(
    *,
    search_callback: Callable[..., list[dict[str, Any]]],
    follow_up_callback: Callable[[str, list[dict[str, Any]]], str],
    before_answer: Callable[[str], None],
    answer_callback: Callable[..., str] | None = None,
):
    """Build a small prepare -> retrieve (MCP) -> generate graph."""
    document_server = build_document_server(search_callback)

    def prepare(state: QuestionState) -> dict[str, Any]:
        started = perf_counter()
        update = {
            "search_question": follow_up_callback(
                state["question"], state.get("history", [])
            )
        }
        trace = list(state.get("trace", []))
        _record(trace, "node.prepare", "ok", started)
        return {**update, "trace": trace}

    async def retrieve(state: QuestionState) -> dict[str, Any]:
        started = perf_counter()
        trace = list(state.get("trace", []))
        tool_trace: list[dict[str, Any]] = []
        search_args = {
            "query": state["search_question"],
            "course_id": state["course_id"],
            "user_id": state["user_id"],
            "limit": 6,
            "page": state.get("page"),
        }
        try:
            passages = await call_document_search(document_server, trace=tool_trace, **search_args)
            trace.extend(tool_trace)
            _record(trace, "node.retrieve", "ok", started)
            return {"passages": passages[:6], "mcp_used": True, "fallback_used": False, "trace": trace}
        except Exception:
            # Preserve Phase 3C availability if MCP is temporarily unavailable.
            trace.extend(tool_trace)
            passages = search_callback(**search_args)
            _record(trace, "node.retrieve_fallback", "ok", started)
            return {"passages": passages[:6], "mcp_used": False, "fallback_used": True, "trace": trace}

    def generate(state: QuestionState) -> dict[str, Any]:
        started = perf_counter()
        trace = list(state.get("trace", []))
        passages = state.get("passages", [])
        if not passages:
            update = {
                "answer": "",
                "error": "No relevant text was found in this course's documents.",
                "mode": "retrieval_only",
            }
            _record(trace, "node.generate", "skipped_no_evidence", started)
            return {**update, "trace": trace}
        # Match Phase 3C: enforce the daily limit after retrieval, before any LLM call.
        combined = bool(re.search(r"compare|comparison", state["question"], re.I) and re.search(r"quiz|mcq", state["question"], re.I))
        if combined and len({p["source"] for p in passages}) != 2:
            return {"answer": "", "error": "Please select or name the two lecture PDFs to compare.", "mode": "retrieval_only", "trace": trace}
        before_answer(state["user_id"])
        try:
            answer_function = answer_callback or generate_answer
            history = state.get("history") or None
            # Keep the legacy two-argument callback usable for regression tests
            # and downstream integrations while passing history when supported.
            combined = bool(re.search(r"compare|comparison", state["question"], re.I) and re.search(r"quiz|mcq", state["question"], re.I))
            def invoke(prompt):
                try:
                    signature(answer_function).bind(prompt, passages, history)
                except (TypeError, ValueError):
                    return answer_function(prompt, passages)
                return answer_function(prompt, passages, history)
            if combined:
                started_compare = perf_counter()
                comparison = invoke("Compare the two selected lectures in a Markdown table: main concepts, similarities, differences and examples. Cite current evidence. State that coverage is limited to retrieved excerpts.")
                _record(trace, "node.compare", "ok", started_compare)
                started_quiz = perf_counter()
                quiz = invoke("Generate a quiz of exactly five MCQs about both selected lectures.")
                _record(trace, "node.generate_quiz", "ok", started_quiz)
                answer = "## Part 1: Lecture Comparison\n\n" + comparison + "\n\n## Part 2: Quiz\n\n" + quiz
            else:
                answer = invoke(state["question"])
            if not answer or not answer.strip():
                raise LLMServiceError("The answer service returned an empty response.")
            update = {"answer": answer, "error": None, "mode": "generated"}
        except LLMServiceError as error:
            update = {"answer": "", "error": str(error), "mode": "retrieval_only"}
        except Exception:
            update = {
                "answer": "The AI answer service encountered a problem. Review the retrieved passages below and try again later.",
                "error": "The AI answer service encountered a problem.",
                "mode": "retrieval_only",
            }
        _record(trace, "node.generate", "ok" if update["mode"] == "generated" else "fallback", started)
        return {**update, "trace": trace}

    graph = StateGraph(QuestionState)
    graph.add_node("prepare", prepare)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
