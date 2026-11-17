import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { hasResearchNote, noteActionLabel, notePaperFor, paperWithSavedNote } from './src/services/researchNotes.js';
import { parseRoute, routeFor, visiblePage } from './src/services/routes.js';

const server = await createServer({ server:{middlewareMode:true}, appType:'custom' });
let passed=0;
function check(name,callback){callback();passed++;console.log('PASS',name);}
function render(Component,props){return renderToStaticMarkup(React.createElement(Component,props));}
let ResearchOutput,ResearchNotes;
try {
 ({ ResearchOutput, ResearchNotes } = await server.ssrLoadModule('/src/pages/Research.jsx'));
 const papers=[
   {id:'paper-alpha',title:'Retrieval Practice Study',note_text:'Compare the retrieval baseline with the hybrid retriever.',note_updated_at:'2026-11-17 09:30:00'},
   {id:'paper-beta',title:'Agentic Workflow Study',note_text:'Check whether the planner remains deterministic.',note_updated_at:'2026-11-17 10:45:00'},
   {id:'paper-empty',title:'Fresh Unread Study',note_text:'',note_updated_at:null}
 ];

 check('previously saved notes are displayed with title and timestamp',()=>{
   const html=render(ResearchNotes,{papers,paperId:'paper-alpha'});
   assert.match(html,/Retrieval Practice Study/);
   assert.match(html,/Compare the retrieval baseline with the hybrid retriever\./);
   assert.match(html,/Last updated 2026-11-17 09:30:00 UTC/);
   assert.match(html,/Edit Note/);
 });
 check('opening a paper shows that paper note, not another paper note',()=>{
   const html=render(ResearchNotes,{papers,paperId:'paper-beta'});
   assert.match(html,/Agentic Workflow Study/);
   assert.match(html,/Check whether the planner remains deterministic\./);
   assert.doesNotMatch(html,/Compare the retrieval baseline/);
   assert.equal(notePaperFor(papers,'paper-beta').id,'paper-beta');
   assert.equal(notePaperFor(papers,'missing-paper'),null);
 });
 check('editing exposes a textarea with save and cancel actions',()=>{
   const html=render(ResearchNotes,{papers,paperId:'paper-alpha',editing:true,draft:'Updated private note'});
   assert.match(html,/Updated private note/);
   assert.match(html,/maxLength="5000"/);
   assert.match(html,/Save changes/);
   assert.match(html,/Cancel editing/);
 });
 check('save confirmation is visible and announced',()=>{
   const html=render(ResearchNotes,{papers,paperId:'paper-alpha',status:'Note saved successfully'});
   assert.match(html,/Note saved successfully/);
   assert.match(html,/role="status"/);
 });
 check('saved note persists after a simulated page refresh',()=>{
   const updated=paperWithSavedNote(papers,{id:'paper-beta',note_text:'Persisted beta note',note_updated_at:'2026-11-18 07:00:00'});
   const refreshed=JSON.parse(JSON.stringify(updated));
   assert.equal(notePaperFor(refreshed,'paper-beta').note_text,'Persisted beta note');
   const html=render(ResearchNotes,{papers:refreshed,paperId:'paper-beta'});
   assert.match(html,/Persisted beta note/);
   assert.match(html,/Last updated 2026-11-18 07:00:00 UTC/);
 });
 check('notes stay associated with their original paper',()=>{
   const updated=paperWithSavedNote(papers,{id:'paper-beta',note_text:'Only beta changed',note_updated_at:'2026-11-18 07:00:00'});
   assert.equal(updated.find(paper=>paper.id==='paper-alpha').note_text,papers[0].note_text);
   assert.equal(updated.find(paper=>paper.id==='paper-beta').note_text,'Only beta changed');
   assert.equal(updated.find(paper=>paper.id==='paper-empty').note_text,'');
 });
 check('saved papers advertise View Notes or Add Note correctly',()=>{
   assert.equal(noteActionLabel(papers[0]),'View Notes');
   assert.equal(noteActionLabel(papers[1]),'View Notes');
   assert.equal(noteActionLabel(papers[2]),'Add Note');
   assert.equal(hasResearchNote(papers[2]),false);
   const source=readFileSync(new URL('./src/pages/Research.jsx',import.meta.url),'utf8');
   assert.match(source,/noteLabel=\{noteActionLabel\(paper\)\}/);
   assert.match(source,/onNotes=\{\(\)=>openNotes\(paper\)\}/);
 });
 check('My Notes sits alongside the existing generated-output tabs',()=>{
   const notesView=React.createElement(ResearchNotes,{papers,paperId:'paper-alpha'});
   const html=render(ResearchOutput,{outputTab:'notes',notesView});
   assert.match(html,/Summary/);
   assert.match(html,/Literature Review/);
   assert.match(html,/Saved outputs/);
   assert.match(html,/My Notes/);
   assert.match(html,/PRIVATE NOTES/);
   assert.match(html,/Retrieval Practice Study/);
   assert.match(html,/aria-selected="true"[^>]*>My Notes/);
 });
 check('existing Generated Output panel still renders summaries',()=>{
   const html=render(ResearchOutput,{output:'## Key findings\n\nHybrid retrieval improved recall.',outputTask:'summary',outputTab:'summary'});
   assert.match(html,/GENERATED OUTPUT/);
   assert.match(html,/Paper summary/);
   assert.match(html,/Key findings/);
   assert.match(html,/Hybrid retrieval improved recall/);
 });
 check('research navigation and protected routes still work',()=>{
   assert.equal(parseRoute('#'+routeFor('research','topic-1')).page,'research');
   assert.equal(parseRoute('#/research/paper-alpha').topicId,'paper-alpha');
   assert.equal(visiblePage(parseRoute('#/research/topic-1'),null),'auth');
   assert.equal(visiblePage(parseRoute('#/research/topic-1'),{}),'research');
 });
 console.log(`${passed} focused research note checks passed.`);
} finally { await server.close(); }
