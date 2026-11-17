import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, BookOpen, Copy, Download, ExternalLink, FileText, FlaskConical, Library, LogOut, Plus, Search, Sparkles, RefreshCw } from 'lucide-react';
import ResponsiveSidebar, { NavigationToggle } from '../components/ResponsiveSidebar.jsx';
import MarkdownAnswer from '../components/MarkdownAnswer.jsx';
import { researchTopics, createResearchTopic, researchTopic, discoverPapers, saveResearchPaper, saveResearchNote, analyzeResearch, exportResearch } from '../services/research.js';
import { hasResearchNote, noteActionLabel, notePaperFor, paperWithSavedNote } from '../services/researchNotes.js';
import { copyDraftText, downloadResearchMarkdown, downloadResearchPdf } from '../services/researchPdf.js';

const OUTPUT_TABS=[['summary','Summary'],['review','Literature Review'],['saved','Saved outputs'],['notes','My Notes']];
const OUTPUT_HEADINGS={summary:'Paper summary',review:'Literature review',saved:'Saved research drafts',notes:'My notes'};
const outputLabel=task=>({summary:'Paper summary',review:'Literature review',compare:'Paper comparison'}[task] || 'Research draft');
const EMPTY_OUTPUT={summary:'Select a saved paper in the library and choose Summarize. The finished summary will appear here.',review:'Select 2–10 saved papers and choose Literature review. The draft will appear here.',saved:'No saved drafts yet. Generated summaries and literature reviews are saved here automatically.'};

export function outputForTab({tab,output='',outputTask='',outputs=[],savedId=''}){
  if(tab==='saved'){const item=outputs.find(entry=>entry.id===savedId);return item?{...item,saved:true}:null;}
  if(output && outputTask===tab)return {task:tab,answer:output,saved:false};
  const item=outputs.find(entry=>entry.task===tab);return item?{...item,saved:true}:null;
}

export function focusGeneratedOutput(panel,heading,reduceMotion=false){
  panel?.scrollIntoView?.({behavior:reduceMotion?'auto':'smooth',block:'start'});
  heading?.focus?.({preventScroll:true});
}

export function ResearchNotes({papers=[],paperId='',draft='',editing=false,onSelectPaper=()=>{},onStartEdit=()=>{},onDraftChange=()=>{},onSave=()=>{},onCancel=()=>{},busy=false,status=''}){
  const selected=notePaperFor(papers,paperId) || papers.find(hasResearchNote) || null;
  return <section className="research-notes" aria-label="My Notes">
    {papers.length>1 && <label className="research-note-picker">Open a paper note<select value={selected?.id || ''} onChange={event=>onSelectPaper(event.target.value)}>{!selected&&<option value="">Choose a saved paper</option>}{papers.map(paper=><option key={paper.id} value={paper.id}>{paper.title} · {hasResearchNote(paper)?'note saved':'no note'}</option>)}</select></label>}
    {selected?<article className="research-note-card">
      <h3>{selected.title}</h3>
      <p className="research-note-meta">{hasResearchNote(selected)?`Last updated ${selected.note_updated_at || 'time unavailable'} UTC`:'No note saved for this paper yet.'}</p>
      {editing?<>
        <label htmlFor="research-note-inline">Your notes</label>
        <textarea id="research-note-inline" autoFocus maxLength={5000} value={draft} onChange={event=>onDraftChange(event.target.value)} placeholder="Write your private notes about this paper…"/>
        <div className="research-note-actions"><button type="button" className="button-primary" disabled={busy} onClick={onSave}>Save changes</button><button type="button" className="button-outline" disabled={busy} onClick={onCancel}>Cancel editing</button></div>
      </>:<>
        <div className="research-note-content" tabIndex={0}>{hasResearchNote(selected)?selected.note_text:'No note yet. Add your first note for this paper.'}</div>
        <div className="research-note-actions"><button type="button" className="button-outline" disabled={busy} onClick={onStartEdit}>{hasResearchNote(selected)?'Edit Note':'Add Note'}</button></div>
      </>}
      {status && <p className="research-note-status" role="status">{status}</p>}
    </article>:<div className="research-output-empty"><FileText size={22}/><p>No saved notes yet. Open a saved paper in the library and choose Add Note.</p></div>}
  </section>;
}

export function ResearchOutput({output='',outputTask='',outputTab='summary',onChangeTab=()=>{},outputs=[],savedId='',onSelectSaved=()=>{},busy=false,headingRef,panelRef,notesView=null,onDownloadPdf=()=>{},onCopyText=()=>{},onDownloadMarkdown=()=>{},exportBusy=false}){
  const visible=outputForTab({tab:outputTab,output,outputTask,outputs,savedId});
  const headingId='research-output-title';
  function keys(event){
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const order=OUTPUT_TABS.map(([id])=>id),index=order.indexOf(outputTab);
    const next=order[event.key==='Home'?0:event.key==='End'?order.length-1:(index+(event.key==='ArrowRight'?1:-1)+order.length)%order.length];
    onChangeTab(next);
    document.getElementById(`output-tab-${next}`)?.focus();
  }
  return <section ref={panelRef} className="research-output" aria-labelledby={headingId}>
    <div className="research-output-head"><div><p className="eyebrow">{outputTab==='notes'?'PRIVATE NOTES':'GENERATED OUTPUT'}</p><h2 id={headingId} ref={headingRef} tabIndex={-1}>{OUTPUT_HEADINGS[outputTab]}</h2></div>
      <div className="research-output-tabs" role="tablist" aria-label="Research output views" onKeyDown={keys}>{OUTPUT_TABS.map(([id,label])=><button key={id} type="button" role="tab" id={`output-tab-${id}`} aria-controls="research-output-panel" aria-selected={outputTab===id} tabIndex={outputTab===id?0:-1} className={outputTab===id?'active':''} onClick={()=>onChangeTab(id)}>{label}{id==='saved'&&outputs.length?` (${outputs.length})`:''}</button>)}</div>
    </div>
    <div className="research-output-body" id="research-output-panel" role="tabpanel" aria-labelledby={`output-tab-${outputTab}`}>
      {outputTab==='notes'?notesView:<>
        {outputTab==='saved'&&outputs.length>0&&<label className="research-output-picker">Open a saved draft<select value={savedId} onChange={event=>onSelectSaved(event.target.value)}><option value="">Choose a draft</option>{outputs.map(item=><option key={item.id} value={item.id}>{outputLabel(item.task)} · {item.created_at} UTC</option>)}</select></label>}
        {visible?<p className="research-output-meta">{visible.saved?'Saved draft':'Newly generated output'} · {outputLabel(visible.task)}{visible.created_at?` · ${visible.created_at} UTC`:''}</p>:<div className="research-output-empty"><FileText size={22}/><p>{outputTab==='saved'&&outputs.length?'Choose a saved draft above to reopen it.':EMPTY_OUTPUT[outputTab]}</p></div>}
        <div className="research-output-actions" role="group" aria-label="Export the displayed draft">
          <button type="button" className="button-primary" disabled={!visible?.answer || exportBusy} onClick={()=>onDownloadPdf(visible)}><Download size={15}/>Download PDF</button>
          <button type="button" className="button-outline" disabled={!visible?.answer || exportBusy} onClick={()=>onCopyText(visible)}><Copy size={15}/>Copy text</button>
          <button type="button" className="button-outline" disabled={!visible?.answer || exportBusy} onClick={()=>onDownloadMarkdown(visible)}><FileText size={15}/>Download Markdown</button>
        </div>
        {visible&&<div className="research-output-content"><MarkdownAnswer text={visible.answer} headingLevel={3}/></div>}
        {busy&&<p className="research-working" role="status">Working on your request. The result will appear here automatically.</p>}
      </>}
    </div>
  </section>;
}

function PaperCard({ paper, saved, selected, onSelect, onSave, onSummary, onNotes, noteLabel, busy, isNew }) {
  return <article className={`research-paper${selected ? ' is-selected' : ''}`}><div className="research-paper-heading"><span className="research-provider">{paper.provider === 'arxiv' ? 'arXiv' : 'Semantic Scholar'} {paper.year ? `· ${paper.year}` : ''}</span>{isNew && <span className="research-badge">Newly discovered</span>}</div>
    <h3><a href={paper.source_url} target="_blank" rel="noopener noreferrer">{paper.title} <ExternalLink size={14}/></a></h3>
    <p className="research-authors">{paper.authors?.join(', ') || 'Author metadata unavailable'}</p>
    <small>{paper.external_id}{paper.doi ? ` · DOI: ${paper.doi}` : ''}{paper.citation_count != null ? ` · ${paper.citation_count} citations` : ''}</small>
    <details><summary>Read abstract</summary><p>{paper.abstract || 'Abstract unavailable from this provider.'}</p></details>
    <div className="research-paper-actions">{saved ? <><label className="research-select"><input type="checkbox" checked={selected} disabled={busy} onChange={onSelect}/> Select paper</label><button className="button-outline" disabled={busy || !paper.abstract} onClick={onSummary}>Summarize</button><button className="button-outline" disabled={busy} onClick={onNotes}>{noteLabel || 'Notes'}</button></> : <button className="button-outline" disabled={busy} onClick={onSave}><Plus size={15}/>Save to topic</button>}</div>
  </article>;
}
export default function Research({ navigate, selectedTopicId='', onLogout }) {
  const [navigationOpen,setNavigationOpen]=useState(false);
  const [topics,setTopics]=useState([]),[data,setData]=useState(null),[title,setTitle]=useState('');
  const [tab,setTab]=useState('discover'),[query,setQuery]=useState(''),[secondary,setSecondary]=useState(false);
  const [results,setResults]=useState([]),[newIds,setNewIds]=useState([]),[selected,setSelected]=useState([]);
  const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [output,setOutput]=useState(''),[outputTask,setOutputTask]=useState(''),[outputTab,setOutputTab]=useState('summary'),[savedOutputId,setSavedOutputId]=useState('');
  const [outputFocus,setOutputFocus]=useState(0),[exportBusy,setExportBusy]=useState(false);
  const [notePaperId,setNotePaperId]=useState(''),[noteDraft,setNoteDraft]=useState(''),[editingNote,setEditingNote]=useState(false),[noteStatus,setNoteStatus]=useState('');
  const pending=useRef(null);
  const outputPanel=useRef(null),outputHeading=useRef(null);
  useEffect(()=>{
    if(!outputFocus)return;
    const reduce=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false;
    focusGeneratedOutput(outputPanel.current,outputTab==='notes'?null:outputHeading.current,reduce);
  },[outputFocus]);
  useEffect(()=>{
    let active=true;
    async function load(){
      try {
        setOutput('');setOutputTask('');setSavedOutputId('');
        setNotePaperId('');setNoteDraft('');setEditingNote(false);setNoteStatus('');
        const list=await researchTopics();if(!active)return;setTopics(list.topics);
        if(!selectedTopicId && list.topics.length){navigate('research',list.topics[0].id,true);return;}
        if(selectedTopicId){const detail=await researchTopic(selectedTopicId);if(active){setData(detail);setQuery(detail.topic.title);}}
      }catch(reason){if(active)setError(reason.message);}finally{if(active)setLoading(false);}
    }
    load();return()=>{active=false;};
  },[selectedTopicId]);
  async function refresh(){const detail=await researchTopic(selectedTopicId);setData(detail);return detail;}
  async function act(callback){if(busy)return;setBusy(true);setError('');setNotice('');try{await callback();}catch(reason){setError(reason.message);}finally{setBusy(false);}}
  async function create(event){event.preventDefault();await act(async()=>{const result=await createResearchTopic(title.trim());navigate('research',result.topic.id);});}
  async function search(event){event?.preventDefault();await act(async()=>{
    const found=await discoverPapers(selectedTopicId,query.trim() || data.topic.title,secondary);
    setResults(found.papers);setNewIds(found.new_ids);setData(current=>({...current,searches:found.searches}));
    const status=found.search_status==='unavailable' ? 'Search providers could not complete this request. This does not mean no papers exist.' : found.papers.length ? `${found.papers.length} results; ${found.new_ids.length} newly discovered for this topic.` : 'The available providers returned no matching papers. Try a shorter academic query.';
    const availability=(found.provider_status || []).map(item=>`${item.provider}: ${item.status.replaceAll('_',' ')}${item.query_used ? ` (searched: ${item.query_used})` : ''}${item.retry_after ? `; wait at least ${item.retry_after} seconds` : ''}.`).join(' ');
    setNotice(`${status} ${found.cached ? (found.papers.length ? 'Cached public metadata (up to one hour old).' : 'Cached empty result (up to one minute old).') : ''} ${availability} ${found.warnings.join(' ')}`);
    setTab('discover');
  });}
  function toggle(id){setSelected(current=>current.includes(id)?current.filter(value=>value!==id):current.length<10?[...current,id]:current);}
  function changeOutputTab(next){
    setOutputTab(next);
    if(next==='saved'&&!savedOutputId&&data?.outputs.length)setSavedOutputId(data.outputs[0].id);
    if(next==='notes'&&!notePaperId){const first=(data?.papers||[]).find(hasResearchNote);if(first){setNotePaperId(first.id);setNoteDraft(first.note_text||'');setEditingNote(false);setNoteStatus('');}}
  }
  async function analyze(task,ids=selected){await act(async()=>{
    const signature=JSON.stringify([selectedTopicId,task,ids]);
    if(pending.current?.signature!==signature)pending.current={signature,id:crypto.randomUUID()};
    const result=await analyzeResearch(selectedTopicId,task,ids,pending.current.id);
    setOutput(result.answer);setOutputTask(task);setOutputTab(task==='summary'?'summary':task==='review'?'review':'saved');setSavedOutputId('');
    pending.current=null;setOutputFocus(value=>value+1);
    const detail=await refresh();if(detail.outputs?.[0])setSavedOutputId(detail.outputs[0].id);
    setNotice('Draft ready. It uses available abstracts, not full PDFs. Review all claims against the original papers.');
  });}
  async function openNotes(paper){setNotePaperId(paper.id);setNoteDraft(paper.note_text || '');setEditingNote(!hasResearchNote(paper));setNoteStatus('');setOutputTab('notes');setOutputFocus(value=>value+1);}
  function selectNotePaper(id){const paper=notePaperFor(data?.papers || [],id);setNotePaperId(id);setNoteDraft(paper?.note_text || '');setEditingNote(false);setNoteStatus('');}
  function editNote(){const paper=notePaperFor(data?.papers || [],notePaperId) || (data?.papers || []).find(hasResearchNote);setNoteDraft(paper?.note_text || '');setEditingNote(true);setNoteStatus('');}
  function cancelNote(){setEditingNote(false);setNoteDraft('');setNoteStatus('');}
  async function saveNoteChanges(){
    const paper=notePaperFor(data?.papers || [],notePaperId) || (data?.papers || []).find(hasResearchNote);
    if(!paper)return;
    await act(async()=>{
      const result=await saveResearchNote(paper.id,noteDraft);
      setData(current=>current?{...current,papers:paperWithSavedNote(current.papers,result.paper)}:current);
      setNoteDraft(result.paper.note_text || '');setEditingNote(false);setNoteStatus('Note saved successfully');setNotice('Note saved successfully');
    });
  }
  async function download(format){await act(async()=>{
    const result=await exportResearch(selectedTopicId,selected,format);
    const url=URL.createObjectURL(new Blob([result.content],{type:'text/plain;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=result.filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });}
  async function exportDraft(visible,format){
    if(!visible?.answer || exportBusy)return;
    setExportBusy(true);setError('');setNotice('');
    try {
      const options={answer:visible.answer,task:visible.task,topicTitle:data?.topic?.title || 'Research topic'};
      if(format==='pdf'){const filename=downloadResearchPdf(options);setNotice(`PDF report downloaded as ${filename}.`);}
      else if(format==='markdown'){const filename=downloadResearchMarkdown(options);setNotice(`Markdown draft downloaded as ${filename}.`);}
      else {await copyDraftText(visible.answer);setNotice('Draft text copied to the clipboard.');}
    } catch(reason){setError(reason?.message || 'The draft could not be exported. Your saved work is unchanged.');}
    finally {setExportBusy(false);}
  }
  return <main className="research-shell"><header className="research-top"><NavigationToggle label="Open research topics" onClick={()=>setNavigationOpen(true)}/><button className="back-link" onClick={()=>navigate('selector')}><ArrowLeft size={16}/> Back to Workspace</button><span className="brand"><FlaskConical size={19}/> Research Environment</span><button className="button-outline research-output-jump" onClick={()=>focusGeneratedOutput(outputPanel.current,outputHeading.current,window.matchMedia('(prefers-reduced-motion: reduce)').matches)}>Outputs &amp; notes</button><button className="button-outline research-signout" aria-label="Sign out" onClick={onLogout}><LogOut size={15}/><span>Sign out</span></button></header>
    <div className="research-layout"><ResponsiveSidebar className="research-sidebar" label="Research topics" open={navigationOpen} onClose={()=>setNavigationOpen(false)}><h2>Research topics</h2><p>Keep each reading project together.</p><form onSubmit={create}><label htmlFor="topic-title">New topic</label><input id="topic-title" required maxLength={120} value={title} onChange={e=>setTitle(e.target.value)} placeholder="e.g. Retrieval-augmented generation"/><button className="button-outline" disabled={busy || !title.trim()}><Plus size={15}/>Create topic</button></form>
      <nav aria-label="Research topics">{topics.map(topic=><button key={topic.id} aria-current={topic.id===selectedTopicId?'page':undefined} className={`side-item ${topic.id===selectedTopicId?'active':''}`} onClick={()=>{setNavigationOpen(false);navigate('research',topic.id);}}><BookOpen size={16}/>{topic.title}</button>)}</nav>
    </ResponsiveSidebar><section className="research-main" tabIndex={0} aria-label="Research content"><div className="welcome"><div><div className="eyebrow">YOUR PRIVATE RESEARCH LIBRARY</div><h1>{data?.topic.title || 'Explore a new idea.'}</h1><p>Discover real papers. Build a thoughtful, source-linked research draft.</p></div></div>
      {error && <div className="api-error" role="alert">{error}<button aria-label="Dismiss error" onClick={()=>setError('')}>×</button></div>}
      {notice && <div className="research-notice" role="status">{notice}</div>}
      {loading ? <p role="status">Loading your research workspace…</p> : !data ? <div className="course-empty"><FlaskConical size={28}/><h2>Create your first research topic</h2><p>Use the topic form to start discovering and saving academic papers.</p></div> : <>
        <nav className="research-tabs" aria-label="Research sections">{[['discover','Discover Papers',Search],['library','Saved Library',Library],['tracking','Research Tracking',RefreshCw]].map(([id,label,Icon])=><button key={id} aria-current={tab===id?'page':undefined} className={tab===id?'active':''} onClick={()=>setTab(id)}><Icon size={16}/>{label}</button>)}</nav>
        {tab==='discover' && <><form className="research-search" onSubmit={search}><label htmlFor="paper-query">Search academic literature</label><div><input id="paper-query" maxLength={300} value={query} onChange={e=>setQuery(e.target.value)} required/><button className="button-primary" disabled={busy}><Search size={16}/>{busy?'Working…':'Discover papers'}</button></div><label className="research-checkbox"><input type="checkbox" checked={secondary} onChange={e=>setSecondary(e.target.checked)} disabled={busy}/> Also search Semantic Scholar (availability may vary)</label><small>Up to 10 results. Public API limits apply; searches are manual.</small></form>
          {results.length===0?<div className="course-empty"><Search size={25}/><h3>Start with a focused topic</h3><p>Search arXiv, read the abstracts, then save useful papers to your private topic.</p></div>:results.map(paper=><PaperCard key={paper.provider+paper.external_id} paper={paper} isNew={newIds.includes(paper.provider+':'+paper.external_id)} busy={busy || data.papers.some(p=>p.provider===paper.provider && p.external_id===paper.external_id)} onSave={()=>act(async()=>{await saveResearchPaper(selectedTopicId,paper);await refresh();setNotice('Paper saved to this topic.');})}/>)}</>}
        {tab==='library' && <><div className="research-selection"><strong>{selected.length} selected</strong><button className="button-outline" disabled={busy || selected.length<2 || selected.length>5} onClick={()=>analyze('compare')}>Compare (2–5)</button><button className="button-primary" disabled={busy || selected.length<2} onClick={()=>analyze('review')}><Sparkles size={15}/>Literature review (2–10)</button><button className="button-outline" disabled={busy || !selected.length} onClick={()=>download('text')}><Download size={14}/>References</button><button className="button-outline" disabled={busy || !selected.length} onClick={()=>download('bibtex')}>BibTeX</button></div>
          {data.papers.length===0?<div className="course-empty"><Library size={25}/><h3>No saved papers yet</h3><p>Discover papers and save them to build your research library.</p><button className="button-outline" onClick={()=>setTab('discover')}>Discover papers</button></div>:data.papers.map(paper=><PaperCard key={paper.id} paper={paper} saved selected={selected.includes(paper.id)} onSelect={()=>toggle(paper.id)} onSummary={()=>analyze('summary',[paper.id])} onNotes={()=>openNotes(paper)} noteLabel={noteActionLabel(paper)} busy={busy}/>)}
        </>}
        {tab==='tracking' && <section className="research-tracking"><h2>Check for New Papers</h2><p>Find papers you have not discovered in this topic before. Newly discovered does not mean newly published.</p><button className="button-primary" disabled={busy} onClick={()=>search()}><RefreshCw size={16}/>Check for New Papers</button><p>Last successful check: {data.searches[0]?.checked_at ? data.searches[0].checked_at+' UTC' : 'Not checked yet'}</p><small>Results may be cached for up to an hour. No background polling or alerts while the app is closed.</small><ul>{data.searches.map((check,i)=><li key={i}><b>{check.search_query}</b><span>{check.result_count} results · {check.checked_at} UTC</span></li>)}</ul></section>}
        <ResearchOutput output={output} outputTask={outputTask} outputTab={outputTab} onChangeTab={changeOutputTab} outputs={data.outputs} savedId={savedOutputId} onSelectSaved={setSavedOutputId} busy={busy} headingRef={outputHeading} panelRef={outputPanel} notesView={<ResearchNotes papers={data.papers} paperId={notePaperId || ((data.papers || []).find(hasResearchNote)?.id || '')} draft={noteDraft} editing={editingNote} onSelectPaper={selectNotePaper} onStartEdit={editNote} onDraftChange={setNoteDraft} onSave={saveNoteChanges} onCancel={cancelNote} busy={busy} status={noteStatus}/>} onDownloadPdf={visible=>exportDraft(visible,'pdf')} onCopyText={visible=>exportDraft(visible,'copy')} onDownloadMarkdown={visible=>exportDraft(visible,'markdown')} exportBusy={exportBusy}/>
      </>}
    </section></div>
  </main>;
}
