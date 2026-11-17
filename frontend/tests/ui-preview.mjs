
import {createServer} from 'vite';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const fixture=fileURLToPath(new URL('./ui-fixtures.js',import.meta.url));
const server=await createServer({root,server:{host:'0.0.0.0',port:5176,strictPort:true,hmr:{port:25176}},plugins:[{name:'isolated-ui-fixtures',enforce:'pre',async load(id){if(['/src/services/api.js','/src/services/research.js','/src/services/auth.js'].some(s=>id.replaceAll('\\','/').endsWith(s)))return await readFile(fixture,'utf8');}}]});
await server.listen();console.log('UI FIXTURES ONLY: http://localhost:5176 — no live API calls.');
