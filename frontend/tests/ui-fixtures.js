
// Fictional in-memory data. Loaded ONLY by tests/ui-preview.mjs; never by production.
const user={id:'ui-student',email:'student@example.test'};
export const authConfigured=true;
export async function getSession(){return sessionStorage.getItem('kp-ui-fixture-login')?{user}:null;}
export function onAuthChange(cb){const f=e=>cb(e.detail);window.addEventListener('kp-ui-fixture-auth',f);return()=>window.removeEventListener('kp-ui-fixture-auth',f);}
export async function signIn(){sessionStorage.setItem('kp-ui-fixture-login','yes');window.dispatchEvent(new CustomEvent('kp-ui-fixture-auth',{detail:user}));return {user,access_token:'fixture-only'};}
export const signUp=signIn;
export async function signOut(){sessionStorage.removeItem('kp-ui-fixture-login');window.dispatchEvent(new CustomEvent('kp-ui-fixture-auth',{detail:null}));}
const courses=[{course_id:'course-ui',name:'Foundations of Machine Learning',document_count:2},{course_id:'course-two',name:'Academic Writing and Research',document_count:1}];
const sources=[{filename:'Machine Learning Notes.pdf',page:12,text:'Retrieval selects relevant passages. Answers must cite the available evidence.'}];
const answer='# Understanding retrieval-augmented generation\n\nA useful answer starts with the evidence. Retrieval brings relevant passages into context so an explanation can stay grounded in course material.\n\n'+Array.from({length:6},(_,i)=>'## '+(i+1)+'. Read, retrieve, reflect\n\nStudents should distinguish a fluent explanation from a supported claim. Compare the answer with its original passage and check the context.\n\n- Keep the original question in view.\n- Compare evidence across sources.\n- Record uncertainty rather than guessing.\n\n').join('')+'## Comparison table\n\n| Approach | Evidence | Strengths | Limitations | Student workflow | Verification |\n|---|---|---|---|---|---|\n'+Array.from({length:5},()=> '| Retrieval augmented generation | Private lecture passages with verifiable references | Grounded and explainable | Depends on indexed documents | Ask a precise question | Open sources and check the page context |\n').join('')+'\n## Key takeaway\n\nUse sources to evaluate the explanation.';
const infographic={title:'From a question to a grounded answer',layout:'overview',introduction:'Follow evidence through the study workflow.',sections:[{heading:'Ask a focused question',body:'A precise question retrieves useful course passages.',icon:'target',definition:'A question scoped to the selected course.'},{heading:'Retrieve evidence',body:'Relevant PDF passages supply the context.',icon:'search',example:'A lecture definition and worked example.'},{heading:'Check the answer',body:'Compare the original context with the generated answer.',icon:'book'}],steps:[],columns:[],similarities:[],differences:[],takeaways:['Keep sources close.','Check important claims.'],source_ids:[1]};
let messages=[{role:'student',text:'Explain retrieval-augmented generation, with a comparison table.'},{role:'assistant',text:answer,sources}];
let sessions=[{session_id:'chat-ui',title:'Retrieval and evidence'},{session_id:'chat-short',title:'A fresh study session'}];
export async function getCourses(){return {courses};}
export async function getCourseDocuments(){return {documents:[{document_id:'doc-ui',filename:'Machine Learning Notes.pdf',page_count:24},{document_id:'doc-two',filename:'Research Methods.pdf',page_count:18}]};}
export async function getChats(){return {sessions};}
export async function getCourseChat(course,id='chat-ui'){return {session_id:id,messages:id==='chat-short'?[]:messages};}
export async function createChat(){return {session_id:'chat-short',title:'New chat'};}
export async function askQuestion(course,text){messages=[...messages,{role:'student',text},{role:'assistant',text:answer,sources}];return {mode:'generated',session_id:'chat-ui'};}
export async function generateInfographic(course,text){messages=[...messages,{role:'student',text},{role:'infographic',infographic,sources}];return {mode:'generated',session_id:'chat-ui'};}
export async function createCourse(name){return {course:{course_id:'fixture-new',name,document_count:0}};}
export async function renameCourse(){return {};}
export async function deleteCourse(){throw Error('Deletion disabled in UI fixtures.');}
export async function deleteDocument(){throw Error('Deletion disabled in UI fixtures.');}
export async function uploadDocument(){throw Error('Uploads disabled in UI fixtures.');}
export async function request(){throw Error('Live API calls disabled in UI fixtures.');}
const topics=[{id:'topic-ui',title:'Evidence-based AI in education'},{id:'topic-two',title:'Accessible digital learning environments'}];
const paper=n=>({id:'paper-'+n,provider:'arxiv',external_id:'fixture-'+n,title:n===1?'Evidence-based tutoring: a framework for grounded educational assistants':'Accessible learning environments and the role of student agency',authors:['A. Student','B. Researcher'],year:2026,citation_count:24,source_url:'https://example.org/paper',abstract:'Fictional abstract for visual acceptance testing only. '+('The study examines academic sources, learner agency and accessible presentation. ').repeat(8),note_text:n===1?'Compare this evidence model with our course readings.':''});
let papers=[paper(1),paper(2)];
let outputs=[{id:'output-ui',task:'summary',answer,created_at:'2026-11-17 12:00:00'},{id:'review-ui',task:'review',answer:'# Literature review\n\n'+answer,created_at:'2026-11-17 12:05:00'}];
export async function researchTopics(){return {topics};}
export async function researchTopic(id){return {topic:topics.find(t=>t.id===id)||topics[0],papers,outputs,searches:[]};}
export async function createResearchTopic(title){return {topic:{id:'topic-ui',title}};}
export async function discoverPapers(){return {papers:[paper(3)],new_ids:['arxiv:fixture-3'],searches:[],warnings:[],provider_status:[],search_status:'ok'};}
export async function saveResearchPaper(topic,p){papers=[...papers,{...p,id:'paper-3'}];return {paper:p};}
export async function saveResearchNote(id,note_text){papers=papers.map(p=>p.id===id?{...p,note_text,note_updated_at:'2026-11-17 12:10:00'}:p);return {paper:papers.find(p=>p.id===id)};}
export async function analyzeResearch(topic,task){const result={id:'output-'+Date.now(),task,answer,created_at:'2026-11-17 12:15:00'};outputs=[result,...outputs];return result;}
export async function exportResearch(){return {content:'Fictional references for UI testing.',filename:'fixture-references.txt'};}
