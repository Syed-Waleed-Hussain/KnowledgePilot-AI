import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseRoute, routeFor, visiblePage } from './src/services/routes.js';

const server = await createServer({ server:{middlewareMode:true}, appType:'custom' });
let passed=0;
function check(name,callback){callback();passed++;console.log('PASS',name);}
try {
 const { default:Environments } = await server.ssrLoadModule('/src/pages/Environments.jsx');
 const { default:Dashboard } = await server.ssrLoadModule('/src/pages/Dashboard.jsx');
 const { default:Research } = await server.ssrLoadModule('/src/pages/Research.jsx');
 const navigate=()=>{};
 const props={navigate,onLogout:()=>{},user:{email:'synthetic@example.test'}};
 const selector=renderToStaticMarkup(React.createElement(Environments,props));
 check('two environment cards',()=>{assert.equal((selector.match(/<article/g)||[]).length,2);assert.match(selector,/Learning Environment/);assert.match(selector,/Research Environment/);});
 check('learning and research actions',()=>{assert.match(selector,/Enter Learning/);assert.match(selector,/Enter Research/);});
 const navigation=[];
 const tree=Environments({...props,navigate:(...args)=>navigation.push(args)});
 function visit(node,callback){if(!React.isValidElement(node))return;callback(node);React.Children.forEach(node.props.children,child=>visit(child,callback));}
 function text(node){if(typeof node==='string')return node;if(!React.isValidElement(node))return '';return React.Children.toArray(node.props.children).map(text).join('');}
 check('learning card opens existing dashboard',()=>{visit(tree,node=>{if(node.type==='button' && text(node)==='Enter Learning')node.props.onClick();});assert.equal(navigation[0][0],'dashboard');});
 check('research card opens research dashboard',()=>{visit(tree,node=>{if(node.type==='button' && text(node)==='Enter Research')node.props.onClick();});assert.equal(navigation[1][0],'research');});
 const learning=renderToStaticMarkup(React.createElement(Dashboard,props));
 const research=renderToStaticMarkup(React.createElement(Research,props));
 check('existing course dashboard retained',()=>{assert.match(learning,/Create course/);assert.match(learning,/My courses/);});
 check('dedicated research dashboard',()=>{assert.match(research,/Research Environment/);assert.match(research,/Research topics/);});
 check('back to workspace in both environments',()=>{assert.match(learning,/Back to Workspace/);assert.match(research,/Back to Workspace/);});
 check('workspace selector route',()=>assert.equal(parseRoute('#'+routeFor('selector')).page,'selector'));
 check('learning route',()=>assert.equal(parseRoute('#'+routeFor('dashboard')).page,'dashboard'));
 check('research route',()=>assert.equal(parseRoute('#'+routeFor('research','topic-1')).topicId,'topic-1'));
 check('refresh preserves course id',()=>assert.equal(parseRoute('#/learning/course/course-1').courseId,'course-1'));
 check('refresh preserves topic id',()=>assert.equal(parseRoute('#/research/topic-1').topicId,'topic-1'));
 check('protected routes require login',()=>{for(const hash of ['#/workspace','#/learning','#/research/topic-1','#/learning/course/course-1'])assert.equal(visiblePage(parseRoute(hash),null),'auth');});
 check('valid session can reopen deep link',()=>assert.equal(visiblePage(parseRoute('#/research/topic-1'),{}),'research'));
 check('unknown route is friendly fallback',()=>assert.equal(parseRoute('#/not-a-route').page,'notfound'));
 check('legacy bookmarks still resolve',()=>{assert.equal(parseRoute('#dashboard').page,'dashboard');assert.equal(parseRoute('#workspace').page,'workspace');assert.equal(parseRoute('#home').page,'home');});
 check('landing anchors retained',()=>{for(const anchor of ['#top','#features','#how'])assert.equal(parseRoute(anchor).page,'home');});
 check('malformed route is safe',()=>assert.equal(parseRoute('#/research/%zz').page,'notfound'));
 console.log(`${passed} frontend render/route checks passed (not browser interaction tests).`);
} finally { await server.close(); }
