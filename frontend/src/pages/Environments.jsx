import { GraduationCap, Microscope, ArrowRight, LogOut, Sparkles } from 'lucide-react';
export default function Environments({ navigate, onLogout }) {
  return <main className="environment-page"><header className="environment-header"><span className="brand"><span className="brand-mark"><Sparkles size={17}/></span>knowledgepilot<span className="brand-ai">AI</span></span><button className="button-outline" onClick={onLogout}><LogOut size={16}/> Sign out</button></header>
    <section className="environment-welcome"><span className="eyebrow">ONE WORKSPACE. TWO WAYS TO EXPLORE.</span><h1>Welcome to KnowledgePilot AI</h1><p>Choose your learning environment.</p></section>
    <div className="environment-grid">{[
      {title:'Learning Environment', Icon:GraduationCap, page:'dashboard', description:'Organize your courses, upload lectures, study with AI, generate quizzes, and track your learning.', features:['My Courses','Lecture Uploads','AI Study Assistant','Summaries','MCQs','Saved Conversations'], button:'Enter Learning'},
      {title:'Research Environment', Icon:Microscope, page:'research', description:'Discover academic papers, organize research topics, compare studies, and generate literature reviews.', features:['Research Topics','Discover Papers','My Research Library','Paper Summaries','Paper Comparison','Literature Reviews','Research Tracking'], button:'Enter Research'},
    ].map(({title,Icon,page,description,features,button})=><article className={`environment-card ${page}`} key={page}><span className="environment-icon"><Icon size={30}/></span><h2>{title}</h2><p>{description}</p><ul>{features.map(feature=><li key={feature}>{feature}</li>)}</ul><button className="button-primary" onClick={()=>navigate(page)}>{button}<ArrowRight size={17}/></button></article>)}</div>
    <p className="environment-footnote">Your courses and research library stay private. Switch environments anytime.</p></main>;
}
