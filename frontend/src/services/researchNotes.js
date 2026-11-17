/** Pure helpers for private research notes. No storage or network access. */
export function hasResearchNote(paper){
  return typeof paper?.note_text==='string' && paper.note_text.trim().length>0;
}

export function noteActionLabel(paper){
  return hasResearchNote(paper)?'View Notes':'Add Note';
}

export function notePaperFor(papers=[],paperId=''){
  return papers.find(paper=>paper.id===paperId) || null;
}

export function paperWithSavedNote(papers=[],saved={}){
  return papers.map(paper=>paper.id===saved.id
    ? {...paper,note_text:saved.note_text ?? paper.note_text,note_updated_at:saved.note_updated_at ?? paper.note_updated_at,generated_summary:saved.generated_summary ?? paper.generated_summary}
    : paper);
}
