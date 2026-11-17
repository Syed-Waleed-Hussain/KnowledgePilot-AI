"""LangGraph orchestration for the existing KnowledgePilot RAG flow."""

import json
import logging
import re
from collections.abc import Callable
from inspect import signature
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agent_harness import AgentRunContext, HarnessError, bounded_context
from backend.rl_retrieval import choose_strategy, retrieval_configuration
from backend.mcp_tools import build_document_server, call_document_search
from backend.chat_memory import is_follow_up
from llm_service import LLMServiceError, generate_answer

logger = logging.getLogger(__name__)


def _record(trace: list[dict[str, Any]], step: str, status: str, started: float) -> None:
    event = {"step": step, "status": status, "duration_ms": round((perf_counter() - started) * 1000, 2)}
    trace.append(event)
    logger.info("phase4_trace step=%s status=%s duration_ms=%.2f", step, status, event["duration_ms"])


class QuestionState(TypedDict, total=False):
    search_limit: int
    run_context: AgentRunContext
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
    output_kind: str
    infographic: dict[str, Any]
    mode: str
    error: str | None
    mcp_used: bool
    fallback_used: bool
    error_category: str
    retry_after: int | None
    document_names: list[str]


def build_question_graph(
    *,
    search_callback: Callable[..., list[dict[str, Any]]],
    follow_up_callback: Callable[[str, list[dict[str, Any]]], str],
    before_answer: Callable[[str], None],
    answer_callback: Callable[..., str] | None = None,
):
    """Build a small prepare -> retrieve (MCP) -> generate graph."""

    def prepare(state: QuestionState) -> dict[str, Any]:
        started = perf_counter()
        update = {
            "search_question": state.get('search_question') or follow_up_callback(
                state["question"], state.get("history", [])
            )
        }
        trace = list(state.get("trace", []))
        context = state.get("run_context")
        if context:
            decision = choose_strategy(state["question"], state.get("history", []), state.get("page"))
            context.retrieval_decision = decision
            if decision:
                resolved_query = update['search_question']
                update["search_question"], update["search_limit"] = retrieval_configuration(
                    decision, state["question"], update["search_question"])
                if is_follow_up(state['question']) and resolved_query != state['question']:
                    update['search_question'] = resolved_query
                trace.append(dict(step="rl.strategy", policy=decision["policy"], mode=decision["mode"],
                    selected_action=decision["selected_action"], executed_action=decision["executed_action"],
                    policy_update="skipped", reason=decision["reason"], status="ok"))
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
            "limit": state.get("search_limit", 6),
            "page": state.get("page"),
        }
        try:
            document_server = build_document_server(search_callback, trusted_user_id=state["user_id"])
            context = state.get("run_context")
            async def execute():
                return await call_document_search(document_server, trace=tool_trace, **search_args)
            passages = await context.tool("search_course_documents", search_args, execute) if context else await execute()
            if not passages and state['search_question'] != state['question']:
                # Retry topic alone, through the same scoped MCP tool and Harness budget.
                search_args['query'] = state['search_question'].split('\nFollow-up:', 1)[0].removeprefix('Previous topic: ')
                passages = await context.tool("search_course_documents", search_args, execute) if context else await execute()
            trace.extend(tool_trace)
            _record(trace, "node.retrieve", "ok", started)
            return {"passages": passages[:6], "mcp_used": True, "fallback_used": False, "trace": trace}
        except Exception:
            if state.get("run_context"):
                raise
            # Preserve Phase 3C availability if MCP is temporarily unavailable.
            trace.extend(tool_trace)
            passages = search_callback(**search_args)
            _record(trace, "node.retrieve_fallback", "ok", started)
            return {"passages": passages[:6], "mcp_used": False, "fallback_used": True, "trace": trace}

    def generate(state: QuestionState) -> dict[str, Any]:
        started = perf_counter()
        trace = list(state.get("trace", []))
        passages = state.get("passages", [])
        context = state.get("run_context")
        if context:
            history, passages = bounded_context(state["question"], state.get("history", []), passages, context.limits)
        else:
            history = state.get("history") or None
        missing_documents = [name for name in state.get('document_names',[]) if name not in {p['source'] for p in passages}]
        if is_follow_up(state['question']) and state['search_question'] == state['question']:
            return dict(answer='', error='Name the topic or lecture first so I can ground this follow-up.',
                        error_category='context_missing', mode='retrieval_only', trace=trace)
        if not passages:
            update = {
                "answer": "",
                "error": "No relevant text was found in this course's documents.",
                "error_category": "context_retrieval" if state['search_question'] != state['question'] else "no_evidence",
                "mode": "retrieval_only",
            }
            _record(trace, "node.generate", "skipped_no_evidence", started)
            return {**update, "trace": trace}
        # Match Phase 3C: enforce the daily limit after retrieval, before any LLM call.
        combined = bool(re.search(r"compare|comparison", state["question"], re.I) and re.search(r"quiz|mcq", state["question"], re.I))
        if combined and len({p["source"] for p in passages}) != 2:
            return {"answer": "", "error": "Please select or name the two lecture PDFs to compare.", "mode": "retrieval_only", "trace": trace}
        if context:
            context.check()
            required = 2 if combined else 1
            if context.model_calls + required > context.limits.models:
                raise HarnessError('budget')
        before_answer(state["user_id"])
        try:
            answer_function = answer_callback or generate_answer
            # Keep the legacy two-argument callback usable for regression tests
            # and downstream integrations while passing history when supported.
            combined = bool(re.search(r"compare|comparison", state["question"], re.I) and re.search(r"quiz|mcq", state["question"], re.I))
            def raw_invoke(prompt):
                try:
                    signature(answer_function).bind(prompt, passages, history)
                except (TypeError, ValueError):
                    return answer_function(prompt, passages)
                return answer_function(prompt, passages, history)
            def invoke(prompt):
                return context.model(lambda: raw_invoke(prompt)) if context else raw_invoke(prompt)
            if combined:
                # Keep the actual student request visible alongside each subtask.
                history = list(history or []) + [{"role": "student", "text": state["question"]}]
                started_compare = perf_counter()
                comparison = invoke("Compare the two selected lectures in a Markdown table: main concepts, similarities, differences and examples. Cite current evidence. State that coverage is limited to retrieved excerpts.")
                _record(trace, "node.compare", "ok", started_compare)
                started_quiz = perf_counter()
                quiz = invoke("Generate a quiz of exactly five MCQs about both selected lectures.")
                _record(trace, "node.generate_quiz", "ok", started_quiz)
                answer = "## Part 1: Lecture Comparison\n\n" + comparison + "\n\n## Part 2: Quiz\n\n" + quiz
            else:
                prompt=state['question']
                if state.get('document_names'):
                    prompt+='\nWrite a practical exam-preparation study plan with a revision schedule and lecture-specific topics. Use only the supplied lecture excerpts and cite evidence from each available lecture. Identify incomplete coverage; do not invent topics.'
                    if missing_documents:prompt+='\nNo usable excerpts were retrieved for: '+', '.join(missing_documents)
                answer = invoke(prompt)
            if not answer or not answer.strip():
                raise LLMServiceError("The answer service returned an empty response.")
            if state.get('output_kind') == 'infographic':
                # The callback validated the schema before this parse. Keep the
                # structured object on the graph state so the route can persist
                # it without ever executing model-generated markup.
                try:
                    infographic = json.loads(answer)
                except (TypeError, ValueError):
                    raise LLMServiceError("The infographic output could not be validated. Try again.", 'invalid_infographic') from None
                if not isinstance(infographic, dict):
                    raise LLMServiceError("The infographic output could not be validated. Try again.", 'invalid_infographic')
                update = {"answer": answer, "infographic": infographic, "error": None, "mode": "generated"}
            else:
                if missing_documents:
                    answer+='\n\n**Coverage limitation:** No usable excerpts were retrieved for '+', '.join(missing_documents)+'. This plan cannot cover that material.'
                elif state.get('document_names'):
                    answer+='\n\n*This plan uses retrieved excerpts. Review the remaining lecture pages for full exam coverage.*'
                update = {"answer": answer, "error": None, "mode": "generated"}
        except HarnessError as error:
            update = dict(answer='', error=str(error), error_category=error.category,
                          retry_after=error.retry_after, mode='retrieval_only')
        except LLMServiceError as error:
            update = dict(answer='', error=str(error), error_category=error.category,
                          retry_after=error.retry_after, mode='retrieval_only')
        except Exception:
            update = {
                "answer": "",
                "error": "The AI answer service encountered a problem.",
                "error_category": "internal",
                "mode": "retrieval_only",
            }
        _record(trace, "node.generate", "ok" if update["mode"] == "generated" else "fallback", started)
        return {**update, "trace": trace, "passages": passages}

    graph = StateGraph(QuestionState)
    graph.add_node("prepare", prepare)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
