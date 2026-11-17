"""Deterministic, metadata-only reference exports and abstract evidence labels."""
import re
from fastapi import HTTPException

def reference(paper):
    parts=[', '.join(paper.get('authors') or []),str(paper['year']) if paper.get('year') else '',paper['title']]
    result='. '.join(part for part in parts if part)+'. '+paper['source_url']
    if paper.get('doi'):result+=' DOI: '+paper['doi']
    return result

def bib_escape(value):
    return ''.join(('\\'+c if c in '\\{}%&_#$' else c) for c in str(value)).replace('\n',' ')

def export_references(papers,format='text'):
    if format=='text':return '\n\n'.join(reference(p) for p in papers)
    entries=[]
    for paper in papers:
        key=re.sub(r'[^A-Za-z0-9]','',paper['provider']+paper['external_id'])
        fields={'title':paper['title'],'url':paper['source_url']}
        if paper.get('authors'):fields['author']=' and '.join(paper['authors'])
        if paper.get('year'):fields['year']=paper['year']
        if paper.get('doi'):fields['doi']=paper['doi']
        if paper['provider']=='arxiv':fields.update(eprint=paper['external_id'],archivePrefix='arXiv')
        entries.append('@misc{'+key+',\n'+',\n'.join('  '+k+' = {'+bib_escape(v)+'}' for k,v in fields.items())+'\n}')
    return '\n\n'.join(entries)

def research_evidence(papers,limits):
    if len(papers)>limits.passage_count:raise HTTPException(422,'This request exceeds the configured research source limit.')
    if not any(p.get('abstract') for p in papers):raise HTTPException(422,'No abstracts are available for these papers. Open the source links for more information.')
    size=min(limits.passage_chars,max(0,(limits.context_chars-2000)//len(papers)-180))
    if size<300:raise HTTPException(422,'The configured research context budget is too small.')
    evidence=[]
    for i,paper in enumerate(papers,1):
        # Short stable source labels leave space for every selected abstract.
        header=f"Title: {paper['title'][:400]}\nID: {paper['provider']}:{paper['external_id']}\n"
        abstract=paper.get('abstract') or 'Not available in the supplied abstract.'
        if paper.get('abstract') and size-len(header)-40<100:
            raise HTTPException(422,'The configured context budget cannot include an abstract excerpt for every selected paper.')
        text=header+'Abstract (possibly excerpted): '+abstract[:max(0,size-len(header)-40)]
        evidence.append(dict(source=f'Research paper R{i}',page='abstract',text=text[:size],similarity=1.0))
    return evidence

def validate_output(task,answer):
    required={'summary':['Research problem','Main objective','Methodology','Key findings','Limitations'],
      'compare':['Comparison','Similarities','Differences'],
      'review':['Introduction','Research background','Major themes','Comparison of approaches','Research gaps','Conclusion']}[task]
    if not all(re.search(r'^#{1,4}\s+(?:\d+[.)]\s*)?'+re.escape(label),answer,re.I|re.M) for label in required):
        raise ValueError('Research output did not contain all required sections.')

def markdown_literal(value):
    text=str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    text=re.sub(r'([\\`*_{}\[\]()~!])',r'\\\1',text)
    return text.replace(':','&#58;')

def render_output(task,answer,papers):
    # Bibliography is built from provider metadata, never from model-written fields.
    answer=re.split(r'^#{1,4}\s+(?:\d+[.)]\s*)?References\b',answer,flags=re.I|re.M)[0].strip()
    answer=re.sub(r'\[(\d+)\]',lambda m:f"[R{m[1]}]({papers[int(m[1])-1]['source_url']})" if 1<=int(m[1])<=len(papers) else '',answer)
    label='Abstract-based summary.' if task=='summary' else 'Abstract-based comparison.' if task=='compare' else 'AI-generated literature-review draft requiring student review. Not an exhaustive review.'
    refs='\n'.join(f"- **R{i}.** {markdown_literal(', '.join(p.get('authors') or []))} "
        f"{('('+str(p['year'])+') ') if p.get('year') else ''}{markdown_literal(p['title'])}. "
        f"[Original paper]({p['source_url']})"
        +(f" DOI: {markdown_literal(p['doi'])}" if p.get('doi') else '') for i,p in enumerate(papers,1))
    return label+' Only supplied abstracts or bounded excerpts were analyzed; full PDFs were not read.\n\n'+answer+'\n\n## References\n\n'+refs
