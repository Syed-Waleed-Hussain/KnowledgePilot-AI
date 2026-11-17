"""Small request-scoped controls; LangGraph remains the orchestrator."""
import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from backend import course_store

@dataclass
class Limits:
    tools: int = field(default_factory=lambda: int(os.getenv('HARNESS_MAX_TOOLS', '5')))
    models: int = field(default_factory=lambda: int(os.getenv('HARNESS_MAX_MODELS', '2')))
    seconds: float = field(default_factory=lambda: float(os.getenv('HARNESS_SECONDS', '30')))
    retries: int = field(default_factory=lambda: int(os.getenv('HARNESS_MAX_RETRIES', '1')))
    history_messages: int = field(default_factory=lambda: int(os.getenv('HARNESS_HISTORY_MESSAGES', '8')))
    history_chars: int = field(default_factory=lambda: int(os.getenv('HARNESS_HISTORY_CHARS', '4000')))
    passage_count: int = field(default_factory=lambda: int(os.getenv('HARNESS_PASSAGE_COUNT', '6')))
    passage_chars: int = field(default_factory=lambda: int(os.getenv('HARNESS_PASSAGE_CHARS', '2000')))
    context_chars: int = field(default_factory=lambda: int(os.getenv('HARNESS_CONTEXT_CHARS', '18000')))

MESSAGES = {
    'research_unavailable': 'The academic search provider could not be reached. Try again later; your saved papers are safe.',
    'research_rate_limit': 'The academic search provider is rate limited. Wait before searching again.',
    'context_missing': 'Please name the topic or lecture first; this conversation has no reliable topic for that follow-up.',
    'context_retrieval': 'I could not find PDF evidence for the previous topic. Name the topic or lecture explicitly and try again.',
    'provider_timeout': 'Groq timed out. Your conversation is saved; retry later.',
    'provider_connection': 'Could not connect to Groq. Your conversation is saved; retry later.',
    'provider_server': 'Groq is temporarily unavailable. Your conversation is saved; retry later.',
    'provider_auth': 'The configured AI credential is invalid or missing. Contact the administrator.',
    'model_unavailable': 'The configured AI model is unavailable. Contact the administrator.',
    'provider_request': 'The AI provider rejected this request. Try a smaller request or contact the administrator.',
    'provider_response': 'Groq returned an empty or unreadable response. Your question is saved; retry later.',
    'app_quota': 'Your daily student AI allowance is exhausted. This is separate from Groq limits.',
    'authentication': 'Please sign in again.',
    'authorization': 'Course unavailable or access denied.',
    'budget': 'This request exceeded its execution budget. Try a smaller request.',
    'timeout': 'This request took too long. Please try again later.',
    'rate_limit': 'Groq rate limit reached for the shared organization. Wait before retrying; this is separate from your student allowance.',
    'service_unavailable': 'The answer service is temporarily unavailable. Try again later.',
    'mcp': 'Document search is temporarily unavailable.',
    'invalid_quiz': 'Quiz output was invalid. Please try a smaller topic.',
    'invalid_infographic': 'The infographic could not be validated against the retrieved evidence. Try a smaller or clearer topic.',
    'validation': 'I found lecture text, but could not verify the answer against its sources. Retry the saved question or name the lecture and topic more precisely.',
    'no_evidence': 'No relevant text was found in this course documents.',
    'internal': 'The request could not be completed. Please try again later.',
}
class HarnessError(RuntimeError):
    def __init__(self, category, retry_after=None):
        self.category = category
        self.retry_after = retry_after
        super().__init__(MESSAGES[category])

def category(error):
    if isinstance(error, HarnessError):
        return error.category
    code = getattr(error, 'status_code', None)
    if getattr(error, 'category', None) in MESSAGES:
        return error.category
    text = str(error).lower()
    if code == 401: return 'authentication'
    if code in (403, 404): return 'authorization'
    if code == 429 or 'rate limit' in text: return 'rate_limit'
    if isinstance(error, TimeoutError) or 'too long' in text: return 'timeout'
    if 'no relevant text' in text: return 'no_evidence'
    if 'unsupported source' in text: return 'validation'
    if 'quiz' in text and 'invalid' in text: return 'invalid_quiz'
    if 'infographic' in text and ('invalid' in text or 'could not be validated' in text): return 'invalid_infographic'
    if isinstance(error, ConnectionError) or code in (502,503,504) or 'temporarily unavailable' in text or 'could not connect' in text:
        return 'service_unavailable'
    return 'internal'

@dataclass
class AgentRunContext:
    user_id: str
    course_id: str
    session_id: str | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    limits: Limits = field(default_factory=Limits)
    tool_calls: int = 0
    model_calls: int = 0
    retries_used: int = 0
    retrieval_decision: dict | None = None
    resource_type: str = "course"
    started: float = field(default_factory=time.perf_counter)
    status: str = 'running'
    error_category: str | None = None
    trace: list = field(default_factory=list)

    def check(self):
        if time.perf_counter() - self.started >= self.limits.seconds:
            raise HarnessError('timeout')

    def authorize(self, tool, args):
        if self.resource_type == 'research_topic':
            from backend.research_store import require_topic
            if tool not in {'search_arxiv_papers', 'search_semantic_scholar', 'list_saved_research_papers'}:
                raise HarnessError('authorization')
            if not self.user_id: raise HarnessError('authentication')
            if args.get('user_id') != self.user_id or args.get('topic_id') != self.course_id:
                raise HarnessError('authorization')
            try:
                require_topic(self.course_id, self.user_id)
            except Exception:
                raise HarnessError('authorization') from None
            return
        if tool != 'search_course_documents': raise HarnessError('authorization')
        if not self.user_id: raise HarnessError('authentication')
        if args.get('user_id') != self.user_id or args.get('course_id') != self.course_id:
            raise HarnessError('authorization')
        if not course_store.course_exists(self.course_id, self.user_id): raise HarnessError('authorization')

    def charge(self, kind):
        self.check()
        attr = 'tool_calls' if kind == 'tool' else 'model_calls'
        maximum = self.limits.tools if kind == 'tool' else self.limits.models
        if getattr(self, attr) >= maximum: raise HarnessError('budget')
        setattr(self, attr, getattr(self, attr) + 1)

    def record(self, step, started, error=None, tool=None):
        self.trace.append(dict(request_id=self.request_id, step=step, tool=tool,
            status='failed' if error else 'ok', duration_ms=round((time.perf_counter()-started)*1000,2),
            error_category=error, tool_calls=self.tool_calls, model_calls=self.model_calls))

    def tool_sync(self, tool, args, callback):
        return self.model(callback, kind='tool', tool=tool, args=args)

    def model(self, callback, *, kind='model', tool=None, args=None):
        if kind not in ('tool', 'model'): raise HarnessError('authorization')
        if kind == 'tool': self.authorize(tool, args or {})
        for attempt in range(min(self.limits.retries, 1) + 1):
            self.charge(kind)
            started = time.perf_counter()
            try:
                result = callback()
                self.check()
                self.record(kind, started, tool=tool)
                return result
            except Exception as error:
                error_kind = category(error)
                self.record('tool' if tool else 'model', started, error_kind, tool)
                if error_kind != 'service_unavailable' or attempt >= min(self.limits.retries, 1) or self.retries_used >= min(self.limits.retries, 1):
                    raise HarnessError(error_kind, getattr(error, 'retry_after', None)) from None
                self.retries_used += 1

    async def tool(self, tool, args, callback):
        self.authorize(tool, args)
        for attempt in range(min(self.limits.retries, 1) + 1):
            self.charge('tool')
            started = time.perf_counter()
            try:
                result = await callback()
                self.check()
                self.record('tool', started, tool=tool)
                return result
            except Exception as error:
                kind = category(error)
                self.record('tool', started, kind, tool)
                if kind != 'service_unavailable' or attempt >= min(self.limits.retries, 1) or self.retries_used >= min(self.limits.retries, 1):
                    raise HarnessError('mcp' if kind == 'internal' else kind) from None
                self.retries_used += 1

    def summary(self):
        return dict(request_id=self.request_id, status=self.status, error_category=self.error_category,
            duration_ms=round((time.perf_counter()-self.started)*1000,2),
            tool_calls=self.tool_calls, model_calls=self.model_calls, trace=self.trace)

def bounded_context(question, history, passages, limits):
    """Character budget (rough token estimate: chars/3); preserve the entire question.

    Metadata remains attached to every retained passage. System instructions are
    constructed separately by llm_service. No new memory store is created.
    """
    remaining = max(0, limits.context_chars - len(question))
    kept_passages = []
    for passage in passages[:limits.passage_count]:
        metadata = {k: passage[k] for k in ('source','page','similarity','document_id') if k in passage}
        overhead = len(str(metadata)) + 80
        size = min(limits.passage_chars, max(0, remaining-overhead))
        if not size: break
        text = passage['text'][:size]
        kept_passages.append(dict(metadata, text=text))
        remaining -= len(text) + overhead
    kept_history = []
    allowance = min(remaining, limits.history_chars)
    for item in reversed(history[-limits.history_messages:]):
        text = item['text'][:min(1000, max(0, allowance-40))]
        if not text: break
        kept_history.insert(0, dict(role=item['role'], text=text))
        allowance -= len(text)+40
    return kept_history, kept_passages

async def run_graph(graph, state, context, *, evaluate_answer_quality=True):
    """Cooperative deadline: a running synchronous SDK call cannot be killed.

    Structured infographics are validated by their own schema and source-ID
    checks, so Markdown citation evaluation can be skipped for that one format.
    Harness, retrieval, MCP and quota controls still run unchanged.
    """
    from backend.phase5_evaluation import evaluate_answer
    state = dict(state, run_context=context)
    state['history'], _ = bounded_context(state['question'], state.get('history', []), [], context.limits)
    try:
        context.authorize('list_saved_research_papers' if context.resource_type == 'research_topic' else 'search_course_documents', state)
        async with asyncio.timeout(context.limits.seconds):
            result = await graph.ainvoke(state)
        context.check()
        if evaluate_answer_quality:
            metrics = evaluate_answer(state['question'], result.get('answer',''), result.get('passages',[]),state.get('document_names',()))
        else:
            generated = result.get('mode') == 'generated' and bool(str(result.get('answer', '')).strip())
            metrics = dict(evidence_available=bool(result.get('passages')), citation_validity=generated,
                structured_output_validity=generated, task_completion=generated,
                passed=generated, failure_reasons=[] if generated else ['incomplete_output'],
                factual_accuracy_evaluated=False, validation_mode='structured_infographic')
        if evaluate_answer_quality and result.get('mode') == 'generated' and not metrics['passed']:
            reasons=metrics['failure_reasons']
            if 'missing_citations' in reasons or 'missing_lecture_citations' in reasons:
                message='The answer did not include verifiable references for the retrieved lectures. Retry this saved question; no extra student allowance will be charged.'
            elif 'unsupported_citations' in reasons:
                message='The answer used source numbers that do not match the retrieved excerpts. Retry this saved question.'
            elif 'invalid_quiz_structure' in reasons:
                message='The quiz response was incomplete. Retry this saved question or request a smaller topic.'
            else:message=MESSAGES['validation']
            result.update(answer='',mode='retrieval_only',error=message,error_category='validation')
        context.status = 'succeeded' if result.get('mode') == 'generated' else 'failed'
        if context.status == 'failed':
            context.error_category = result.get('error_category') or category(RuntimeError(result.get('error','')))
            if context.error_category!='validation' or not result.get('error'):
                result['error'] = MESSAGES[context.error_category]
        result['evaluation'] = metrics
    except Exception as error:
        # Preserve existing HTTP quota errors and their status codes.
        if getattr(error, 'status_code', None) in (409,429): raise
        context.status, context.error_category = 'failed', category(error)
        result = dict(answer='', passages=[], mode='retrieval_only', error=MESSAGES[context.error_category],
                      retry_after=getattr(error, 'retry_after', None))
    context.record('run', context.started, context.error_category)
    result.setdefault('evaluation', evaluate_answer(state['question'], '', []))
    result['evaluation'].update(duration_ms=context.summary()['duration_ms'],
        tool_calls=context.tool_calls, model_calls=context.model_calls,
        success=context.status == 'succeeded')
    if context.retrieval_decision:
        from backend.rl_retrieval import finish_decision
        context.trace.append(finish_decision(context.retrieval_decision, result['evaluation']))
    result['reliability'] = context.summary()
    result['error_category'] = context.error_category
    result['retryable'] = context.error_category in ('validation','invalid_quiz','invalid_infographic','rate_limit', 'provider_timeout', 'provider_connection', 'provider_server', 'provider_response', 'provider_auth', 'model_unavailable', 'timeout', 'mcp', 'service_unavailable', 'internal')
    return result
