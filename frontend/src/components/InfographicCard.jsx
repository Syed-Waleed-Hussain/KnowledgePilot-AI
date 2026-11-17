import { useState } from 'react';
import {
  ArrowDown, BookOpen, Boxes, Brain, Check, Clock, Compass, Copy, Cpu, Database,
  FileDown, FileText, GitBranch, Layers, Lightbulb, List, Network, Puzzle,
  RefreshCw, Scale, Search, Settings, Shield, Sparkles, Target, Users, Workflow, Zap
} from 'lucide-react';
import { copyDraftText, downloadInfographicPdf } from '../services/researchPdf.js';
import {
  infographicLayoutLabel, infographicSummaryText, normalizeInfographic, referencedSources
} from '../services/infographic.js';

const ICONS = {
  sparkles: Sparkles, layers: Layers, target: Target, book: BookOpen, cpu: Cpu,
  workflow: Workflow, check: Check, lightbulb: Lightbulb, 'git-branch': GitBranch,
  shield: Shield, database: Database, brain: Brain, list: List, refresh: RefreshCw,
  settings: Settings, users: Users, zap: Zap, search: Search, 'file-text': FileText,
  scale: Scale, boxes: Boxes, compass: Compass, puzzle: Puzzle, clock: Clock,
  network: Network, 'arrow-right': ArrowDown
};

function Icon({ name, size = 18 }) {
  const Component = ICONS[name] || Sparkles;
  return <Component size={size} aria-hidden="true" />;
}

function ConceptCards({ sections, title = 'Concept cards' }) {
  if (!sections.length) return null;
  return <section className="infographic-section" aria-label={title}>
    <h3 className="infographic-section-title">{title}</h3>
    <div className="infographic-overview">
      {sections.map((section, index) => <article className={`infographic-card-item tone-${index % 4}`} key={`${section.heading}-${index}`}>
        <div className="infographic-card-head">
          <span className="infographic-icon"><Icon name={section.icon} /></span>
          <h4>{section.heading}</h4>
        </div>
        <p>{section.body}</p>
        {section.definition && <div className="infographic-definition"><b>Definition</b><span>{section.definition}</span></div>}
        {section.example && <div className="infographic-example"><b>Example</b><span>{section.example}</span></div>}
      </article>)}
    </div>
  </section>;
}

function ProcessFlow({ steps }) {
  return <section className="infographic-section" aria-label="Process flow"><h3 className="infographic-section-title">Process flow</h3>
    <ol className="infographic-process">
      {steps.map((step, index) => <li className="infographic-step" key={`${step.title}-${index}`}>
        <article className={`infographic-card-item tone-${index % 4}`}>
          <div className="infographic-card-head">
            <span className="infographic-step-number">{index + 1}</span>
            <span className="infographic-icon"><Icon name={step.icon} /></span>
            <h4>{step.title}</h4>
          </div>
          <p>{step.detail}</p>
        </article>
        {index < steps.length - 1 && <span className="infographic-arrow" aria-hidden="true"><ArrowDown size={17} /></span>}
      </li>)}
    </ol>
  </section>;
}

function Comparison({ infographic }) {
  const columnCount = Math.max(1, infographic.columns.length);
  return <section className="infographic-section" aria-label="Comparison"><h3 className="infographic-section-title">Comparison</h3>
    <div className="infographic-compare" style={{ '--columns': columnCount }}>
      {infographic.columns.map((column, index) => <article className={`infographic-column tone-${index % 4}`} key={`${column.title}-${index}`}>
        <h4>{column.title}</h4>
        <ul>{column.points.map(point => <li key={point}>{point}</li>)}</ul>
      </article>)}
    </div>
    <div className="infographic-split">
      <article className="infographic-similar">
        <h4>Similarities</h4>
        <ul>{infographic.similarities.map(item => <li key={item}>{item}</li>)}</ul>
      </article>
      <article className="infographic-different">
        <h4>Differences</h4>
        <ul>{infographic.differences.map(item => <li key={item}>{item}</li>)}</ul>
      </article>
    </div>
  </section>;
}

export default function InfographicCard({ infographic, sources = [], courseName = '', onOpenSources }) {
  const [status, setStatus] = useState('');
  const document = normalizeInfographic(infographic, sources.length);

  if (!document) {
    return <div className="infographic-card infographic-fallback" role="status">
      <div className="infographic-badge"><Sparkles size={14} /> GROUNDED INFOGRAPHIC</div>
      <p>This saved infographic could not be displayed safely. Ask again to regenerate it.</p>
    </div>;
  }

  const references = referencedSources(document, sources);

  function exportPdf() {
    setStatus('');
    try {
      downloadInfographicPdf({ infographic: document, sources, courseName, exportedAt: new Date() });
      setStatus('PDF downloaded.');
    } catch (error) {
      setStatus(error.message || 'PDF export is unavailable in this browser.');
    }
  }

  async function copySummary() {
    setStatus('');
    try {
      await copyDraftText(infographicSummaryText(document, sources));
      setStatus('Summary copied.');
    } catch (error) {
      setStatus(error.message || 'Clipboard access is unavailable.');
    }
  }

  return <article className="infographic-card" aria-label={`Infographic: ${document.title}`}>
    <header className="infographic-top">
      <div>
        <div className="infographic-badge"><Sparkles size={14} /> GROUNDED INFOGRAPHIC</div>
        <h2 className="infographic-title">{document.title}</h2>
        <span className="infographic-layout">{infographicLayoutLabel(document.layout)}</span>
      </div>
      <div className="infographic-actions">
        <button type="button" onClick={exportPdf}><FileDown size={15} /> Download PDF</button>
        <button type="button" onClick={copySummary}><Copy size={15} /> Copy summary</button>
        {onOpenSources && references.length > 0 && <button type="button" onClick={() => onOpenSources(sources)}><BookOpen size={15} /> Sources ({sources.length})</button>}
      </div>
    </header>

    <p className="infographic-intro">{document.introduction}</p>

    {document.layout === 'overview' && <ConceptCards sections={document.sections} />}
    {document.layout === 'process' && <>
      <ProcessFlow steps={document.steps} />
      {document.sections.length > 0 && <ConceptCards sections={document.sections} title="Key concepts" />}
    </>}
    {document.layout === 'comparison' && <>
      <Comparison infographic={document} />
      {document.sections.length > 0 && <ConceptCards sections={document.sections} title="Key concepts" />}
    </>}

    <section className="infographic-takeaways" aria-label="Key takeaways">
      <h3><Lightbulb size={16} /> Key takeaways</h3>
      <ul>{document.takeaways.map(item => <li key={item}>{item}</li>)}</ul>
    </section>

    {references.length > 0 && <section className="infographic-refs" aria-label="Verified sources">
      <h3><FileText size={15} /> Verified sources</h3>
      <ol>{references.map(({ id, source }) => <li key={`${id}-${source.filename}-${source.page}`}>
        <b>[{id}]</b> <span>{source.filename}</span> <small>page {source.page}</small>
      </li>)}</ol>
    </section>}

    {status && <p className="infographic-status" role="status">{status}</p>}
  </article>;
}
