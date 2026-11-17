import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const css=await readFile(new URL('../src/styles.css',import.meta.url),'utf8');
const token=name=>css.match(new RegExp('--'+name+':\\s*(#[0-9a-fA-F]{6})'))?.[1];
function luminance(hex){const rgb=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;}
const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
let count=0;const check=(name,fn)=>{fn();count++;console.log('PASS',name);};
for(const foreground of ['color-primary-text','color-secondary-text','color-tertiary-text','color-accent'])for(const surface of ['color-background','color-surface','color-surface-raised'])check(`${foreground} on ${surface} meets text AA`,()=>assert.ok(contrast(token(foreground),token(surface))>=4.5));
check('primary button text meets text AA',()=>assert.ok(contrast(token('color-background'),token('color-accent'))>=4.5));
check('control edge meets non-text contrast on raised surface',()=>assert.ok(contrast(token('color-control-border'),token('color-surface-raised'))>=3));
check('no remote font dependency',()=>assert.ok(!/@import|fonts\.googleapis|fonts\.gstatic/.test(css)));
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
try{
 const {default:MarkdownAnswer}=await server.ssrLoadModule('/src/components/MarkdownAnswer.jsx');
 const html=renderToStaticMarkup(React.createElement(MarkdownAnswer,{text:'| Concept | Evidence |\n|---|---|\n| Unicode اردو | [source](https://example.org) |'}));
 check('table is a keyboard-accessible scroll region with semantic cells',()=>{assert.match(html,/role="region"/);assert.match(html,/tabindex="0"/);assert.match(html,/<table>/);assert.match(html,/<th>/);assert.match(html,/<td>/);assert.match(html,/اردو/);});
 const {default:Sidebar}=await server.ssrLoadModule('/src/components/ResponsiveSidebar.jsx');
 check('navigation can render without a browser window',()=>assert.match(renderToStaticMarkup(React.createElement(Sidebar,{className:'sidebar',label:'Course navigation',open:false,onClose(){}},'Courses')),/aria-label="Course navigation"/));
 console.log(`${count} UI accessibility/render checks passed. Browser matrix is recorded separately.`);
}finally{await server.close();}
