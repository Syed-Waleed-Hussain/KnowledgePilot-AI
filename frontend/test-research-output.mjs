import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const server = await createServer({ server:{middlewareMode:true}, appType:'custom' });
let passed=0;
function check(name,callback){callback();passed++;console.log('PASS',name);}
const render=props=>renderToStaticMarkup(React.createElement(ResearchOutput,props));
let ResearchOutput,outputForTab,focusGeneratedOutput;
try {
 ({ ResearchOutput, outputForTab, focusGeneratedOutput } = await server.ssrLoadModule('/src/pages/Research.jsx'));
 const summary='## Key findings\n\nThe study reports a 12% improvement [1].';
 const review='## Major themes\n\nEvidence remains mixed across studies [2].';
 const outputs=[
   {id:'out-review',task:'review',answer:review,created_at:'2026-11-17 10:00:00'},
   {id:'out-compare',task:'compare',answer:'Comparison draft',created_at:'2026-11-16 09:00:00'},
   {id:'out-summary',task:'summary',answer:'Older saved summary',created_at:'2026-11-15 08:00:00'}
 ];

 check('four output controls are visible',()=>{
   const html=render({output:summary,outputTask:'summary',outputTab:'summary'});
   assert.match(html,/Summary/);
   assert.match(html,/Literature Review/);
   assert.match(html,/Saved outputs/);
   assert.match(html,/My Notes/);
   assert.match(html,/role="tablist"/);
 });
 check('newly generated summary renders near the top panel',()=>{
   const html=render({output:summary,outputTask:'summary',outputTab:'summary'});
   assert.match(html,/GENERATED OUTPUT/);
   assert.match(html,/Paper summary/);
   assert.match(html,/Newly generated output/);
   assert.match(html,/Key findings/);
   assert.match(html,/12% improvement/);
   assert.match(html,/aria-selected="true"[^>]*>Summary/);
 });
 check('review tab shows generated review',()=>{
   const html=render({output:review,outputTask:'review',outputTab:'review'});
   assert.match(html,/Literature review/);
   assert.match(html,/Major themes/);
   assert.match(html,/Newly generated output/);
 });
 check('saved outputs keep summaries, reviews and comparisons',()=>{
   const html=render({outputTab:'saved',outputs,savedId:'out-review'});
   assert.match(html,/Saved research drafts/);
   assert.match(html,/Saved outputs \(3\)/);
   assert.match(html,/Paper summary · 2026-11-15 08:00:00 UTC/);
   assert.match(html,/Literature review · 2026-11-17 10:00:00 UTC/);
   assert.match(html,/Paper comparison · 2026-11-16 09:00:00 UTC/);
   assert.match(html,/Saved draft · Literature review/);
   assert.match(html,/Major themes/);
 });
 check('empty output areas explain the next step',()=>{
   const summary=render({outputTab:'summary'});
   const saved=render({outputTab:'saved',outputs});
   assert.match(summary,/Select a saved paper in the library and choose Summarize/);
   assert.match(saved,/Choose a saved draft above to reopen it/);
 });
 check('busy state stays inside the visible output panel',()=>{
   const html=render({outputTab:'summary',busy:true});
   assert.match(html,/The result will appear here automatically/);
 });
 check('tab resolver prefers the new draft then falls back to saved output',()=>{
   assert.equal(outputForTab({tab:'summary',output:summary,outputTask:'summary',outputs}).answer,summary);
   assert.equal(outputForTab({tab:'review',output:summary,outputTask:'summary',outputs}).answer,review);
   assert.equal(outputForTab({tab:'saved',outputs,savedId:'out-summary'}).answer,'Older saved summary');
   assert.equal(outputForTab({tab:'saved',outputs,savedId:'missing'}),null);
 });
 check('new output scrolls into view and focuses the heading',()=>{
   const calls=[];
   const panel={scrollIntoView:options=>calls.push(['scroll',options])};
   const heading={focus:options=>calls.push(['focus',options])};
   focusGeneratedOutput(panel,heading,false);
   focusGeneratedOutput(panel,heading,true);
   assert.deepEqual(calls,[
     ['scroll',{behavior:'smooth',block:'start'}],
     ['focus',{preventScroll:true}],
     ['scroll',{behavior:'auto',block:'start'}],
     ['focus',{preventScroll:true}]
   ]);
 });
 check('focus helper is safe when refs are not mounted',()=>{
   focusGeneratedOutput(null,null,false);
 });
 check('research actions precede the output reader in the page source',()=>{
   const source=readFileSync(new URL('./src/pages/Research.jsx',import.meta.url),'utf8');
   assert.ok(source.indexOf('<ResearchOutput')>-1);
   assert.ok(source.indexOf('<ResearchOutput')>source.indexOf('research-tabs'));
   assert.ok(source.indexOf('focusGeneratedOutput(outputPanel.current')>-1);
 });
 console.log(`${passed} focused research output checks passed.`);
} finally { await server.close(); }

