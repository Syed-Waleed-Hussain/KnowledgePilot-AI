"""Authenticated research routes. Providers are fixed; no client-supplied metadata is saved."""
import hashlib
import json
import os
import uuid
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from backend import course_store, research_store as store
from backend.agent_harness import AgentRunContext, Limits, HarnessError, MESSAGES, category
from backend.supabase_auth import get_current_user
from backend.research_graph import build_discovery_graph, build_research_graph
from backend.research_quality import render_output, export_references
from backend.phase5_evaluation import evaluate_answer

class StrictInput(BaseModel):model_config=ConfigDict(extra='forbid')
class TopicInput(StrictInput):title:str=Field(min_length=1,max_length=120)
class SearchInput(StrictInput):
    topic_id:str=Field(min_length=1,max_length=80)
    query:str=Field(min_length=1,max_length=300)
    secondary:bool=False
class SaveInput(StrictInput):
    topic_id:str=Field(min_length=1,max_length=80)
    provider:Literal['arxiv','semantic_scholar']
    external_id:str=Field(min_length=1,max_length=120)
class NoteInput(StrictInput):note_text:str=Field(max_length=5000)
class AnalysisInput(StrictInput):
    topic_id:str=Field(min_length=1,max_length=80)
    task:Literal['summary','compare','review']
    paper_ids:list[str]=Field(min_length=1,max_length=10)
    request_id:str=Field(min_length=1,max_length=80)
class ExportInput(StrictInput):
    topic_id:str=Field(min_length=1,max_length=80)
    paper_ids:list[str]=Field(min_length=1,max_length=100)
    format:Literal['text','bibtex']='text'

def research_context(user_id,topic_id,request_id=None):
    limits=Limits()
    limits.passage_count=max(1,min(10,int(os.getenv('HARNESS_RESEARCH_PASSAGES','10'))))
    return AgentRunContext(user_id=user_id,course_id=topic_id,request_id=request_id or uuid.uuid4().hex,
                           resource_type='research_topic',limits=limits)

def safe_failure(ctx,error):
    ctx.status='failed';ctx.error_category=category(error)
    ctx.record('research.run',ctx.started,ctx.error_category)
    if isinstance(error,HTTPException):raise error
    status=429 if ctx.error_category in ('rate_limit','research_rate_limit') else 403 if ctx.error_category in ('authorization','authentication') else 503
    raise HTTPException(status,dict(message=MESSAGES[ctx.error_category],reliability=ctx.summary())) from None

def create_router(reserve_daily_question):
    router=APIRouter(prefix='/research',tags=['Research'])
    @router.get('/topics')
    def list_topics(user=Depends(get_current_user)):return dict(topics=store.topics(user['id']))
    @router.post('/topics',status_code=201)
    def add_topic(request:TopicInput,user=Depends(get_current_user)):return dict(topic=store.create_topic(request.title,user['id']))
    @router.get('/topics/{topic_id}')
    def topic_detail(topic_id:str,user=Depends(get_current_user)):
        return dict(topic=store.require_topic(topic_id,user['id']),papers=store.list_papers(topic_id,user['id']),
                    searches=store.search_history(topic_id,user['id']),outputs=store.outputs(topic_id,user['id']))
    @router.post('/discover')
    def discover(request:SearchInput,user=Depends(get_current_user)):
        store.require_topic(request.topic_id,user['id'])
        query=request.query.strip()
        if not query:raise HTTPException(422,'Enter a research query.')
        # Search attempts have their own local cap; they do not charge AI quota.
        with course_store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS research_search_usage(user_id TEXT,day TEXT,attempts INTEGER,PRIMARY KEY(user_id,day))')
            row=db.execute('SELECT attempts FROM research_search_usage WHERE user_id=? AND day=?',(user['id'],date.today().isoformat())).fetchone()
            if row and row[0]>=30:raise HTTPException(429,'You have reached today\'s 30 research-search limit.')
            db.execute('INSERT INTO research_search_usage VALUES (?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET attempts=attempts+1',(user['id'],date.today().isoformat()))
        ctx=research_context(user['id'],request.topic_id)
        ctx.limits.retries=0  # Provider pacing/429 information must never be bypassed.
        try:
            result=build_discovery_graph().invoke(dict(topic_id=request.topic_id,user_id=user['id'],query=query,secondary=request.secondary,run_context=ctx))
            ctx.check()
            available=result.get('search_status')!='unavailable'
            if not available:ctx.error_category='research_unavailable'
            new_ids=store.record_search(request.topic_id,user['id'],query,result['results']) if available else []
            ctx.status='succeeded' if available else 'failed';ctx.record('research.discover',ctx.started,None if available else 'research_unavailable')
            return dict(papers=result['results'],new_ids=new_ids,warnings=result['warnings'],cached=result['cached'],
                        provider_status=result.get('provider_status',[]),search_status=result.get('search_status','results' if result['results'] else 'empty'),
                        searches=store.search_history(request.topic_id,user['id']),reliability=ctx.summary())
        except Exception as error:safe_failure(ctx,error)
    @router.post('/papers',status_code=201)
    def save(request:SaveInput,user=Depends(get_current_user)):
        return dict(paper=store.save_paper(request.topic_id,user['id'],request.provider,request.external_id))
    @router.get('/papers/{paper_id}')
    def paper_detail(paper_id:str,user=Depends(get_current_user)):return dict(paper=store.get_paper(paper_id,user['id']))
    @router.patch('/papers/{paper_id}/notes')
    def notes(paper_id:str,request:NoteInput,user=Depends(get_current_user)):
        return dict(paper=store.save_note(paper_id,user['id'],text=request.note_text))
    @router.post('/analyze')
    def analyze(request:AnalysisInput,user=Depends(get_current_user)):
        count=len(request.paper_ids)
        if (request.task=='summary' and count!=1) or (request.task=='compare' and not 2<=count<=5) or (request.task=='review' and not 2<=count<=10):
            raise HTTPException(422,'Select one paper for a summary, 2–5 for comparison, or 2–10 for a literature review.')
        # Ownership checks occur before replay, quota reservation or model execution.
        store.selected_papers(request.topic_id,user['id'],request.paper_ids)
        key='research:'+request.request_id
        signature=json.dumps([request.topic_id,request.task,request.paper_ids],separators=(',',':'))
        with course_store.connect() as db:
            saved=db.execute('SELECT * FROM research_outputs WHERE user_id=? AND request_key=?',(user['id'],key)).fetchone()
        if saved:
            if saved['topic_id']!=request.topic_id or saved['task']!=request.task or json.loads(saved['paper_ids_json'])!=request.paper_ids:
                raise HTTPException(409,'This request ID already belongs to a different analysis.')
            return dict(answer=saved['answer'],replayed=True)
        ctx=research_context(user['id'],request.topic_id)
        def reserve(uid):reserve_daily_question(uid,key,hashlib.sha256(signature.encode()).hexdigest())
        try:
            result=build_research_graph(reserve).invoke(dict(topic_id=request.topic_id,user_id=user['id'],task=request.task,
                paper_ids=request.paper_ids,question='Research '+request.task,run_context=ctx))
            ctx.check()
            evaluation=evaluate_answer('Research '+request.task,result['answer'],result['passages'])
            if not evaluation['passed']:raise HarnessError('validation')
            answer=render_output(request.task,result['answer'],result['papers'])
            with course_store.connect() as db:
                db.execute('INSERT OR IGNORE INTO research_outputs(id,user_id,topic_id,task,paper_ids_json,answer,request_key) VALUES (?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex,user['id'],request.topic_id,request.task,json.dumps(request.paper_ids),answer,key))
            if request.task=='summary':store.save_note(request.paper_ids[0],user['id'],summary=answer)
            ctx.status='succeeded';ctx.record('research.analyze',ctx.started)
            return dict(answer=answer,evaluation=evaluation,reliability=ctx.summary(),replayed=False)
        except Exception as error:safe_failure(ctx,error)
    @router.post('/export')
    def export(request:ExportInput,user=Depends(get_current_user)):
        papers=store.selected_papers(request.topic_id,user['id'],request.paper_ids)
        return dict(content=export_references(papers,request.format),filename='research-references.'+('bib' if request.format=='bibtex' else 'txt'))
    return router
