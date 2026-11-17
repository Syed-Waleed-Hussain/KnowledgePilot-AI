import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const here = dirname(fileURLToPath(import.meta.url));
const artifacts = resolve(here, '.infographic-test-artifacts');
rmSync(artifacts, { recursive: true, force: true });
mkdirSync(artifacts, { recursive: true });

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
let passed = 0;
function check(name, callback) { callback(); passed += 1; console.log('PASS', name); }
function render(Component, props) { return renderToStaticMarkup(React.createElement(Component, props)); }
function writeArtifact(name, bytes) { return writeFileSync(resolve(artifacts, name), bytes); }
function buildPdf(options) {
  const bytes = buildInfographicPdf(options);
  const text = Buffer.from(bytes).toString('latin1');
  assert.ok(text.startsWith('%PDF-1.4'), 'PDF signature is missing');
  assert.match(text, /%%EOF\s*$/, 'PDF end marker is missing');
  return bytes;
}

const SOURCES = [
  { filename: 'Lecture13.pdf', page: 4, text: 'Job Design defines tasks, responsibilities and relationships.' },
  { filename: 'Lecture13.pdf', page: 5, text: 'Job enrichment adds responsibility and autonomy to a role.' }
];

const OVERVIEW = {
  title: 'Job Design Essentials',
  layout: 'overview',
  introduction: 'Job design defines tasks, responsibilities and relationships in a role.',
  sections: [
    { heading: 'Task scope', body: 'Job design specifies the tasks and responsibilities of a role.', icon: 'target',
      definition: 'The process of organising work.', example: 'A production team rotates tasks.' },
    { heading: 'Skill variety', body: 'Job rotation develops employee skills across different tasks.', icon: 'refresh' },
    { heading: 'Autonomy', body: 'Job enrichment adds responsibility and autonomy to a role.', icon: 'shield' }
  ],
  steps: [], columns: [], similarities: [], differences: [],
  takeaways: ['Job design shapes responsibilities.', 'Rotation builds skills.'],
  source_ids: [1]
};
const PROCESS = {
  title: 'Grounded RAG Flow',
  layout: 'process',
  introduction: 'A retrieval-augmented generation pipeline retrieves evidence before answering.',
  sections: [],
  steps: [
    { title: 'Prepare the question', detail: 'The student question is normalised for retrieval.', icon: 'settings' },
    { title: 'Retrieve evidence', detail: 'Course PDF passages are filtered by owner and course.', icon: 'search' },
    { title: 'Generate the answer', detail: 'The model answers only from the retrieved evidence.', icon: 'sparkles' }
  ],
  columns: [], similarities: [], differences: [],
  takeaways: ['Retrieval happens before generation.', 'Evidence stays course-scoped.'],
  source_ids: [1, 2]
};
const COMPARISON = {
  title: 'Job Rotation vs Job Enlargement',
  layout: 'comparison',
  introduction: 'Job rotation and job enlargement change work in different ways.',
  sections: [], steps: [],
  columns: [
    { title: 'Job rotation', points: ['Moves between tasks', 'Builds broad skills'] },
    { title: 'Job enlargement', points: ['Adds related tasks', 'Increases task variety'] }
  ],
  similarities: ['Both change task scope.', 'Both aim to improve motivation.'],
  differences: ['Rotation changes roles.', 'Enlargement adds tasks.'],
  takeaways: ['Rotation builds breadth.', 'Enlargement adds depth.'],
  source_ids: [1, 2]
};

let InfographicCard, normalizeInfographic, infographicLayoutLabel, referencedSources,
  infographicSummaryText, buildInfographicPdf, infographicPdfFilename, planFiles = [];
try {
  ({ default: InfographicCard } = await server.ssrLoadModule('/src/components/InfographicCard.jsx'));
  ({
    normalizeInfographic, infographicLayoutLabel, referencedSources, infographicSummaryText
  } = await server.ssrLoadModule('/src/services/infographic.js'));
  ({ buildInfographicPdf, infographicPdfFilename } = await server.ssrLoadModule('/src/services/researchPdf.js'));
  const { displayMessages, infographicPrompt, DEFAULT_INFOGRAPHIC_PROMPT } = await server.ssrLoadModule('/src/pages/Workspace.jsx');
  const source = readFileSync(resolve(here, 'src/pages/Workspace.jsx'), 'utf8');
  const cardSource = readFileSync(resolve(here, 'src/components/InfographicCard.jsx'), 'utf8');
  const apiSource = readFileSync(resolve(here, 'src/services/api.js'), 'utf8');
  const styleSource = readFileSync(resolve(here, 'src/styles.css'), 'utf8');

  check('all three layouts render as grounded infographic cards', () => {
    const overview = render(InfographicCard, { infographic: OVERVIEW, sources: SOURCES, courseName: 'PPIT' });
    assert.match(overview, /Job Design Essentials/);
    assert.match(overview, /Concept overview/);
    assert.match(overview, /Definition/);
    assert.match(overview, /Example/);
    assert.match(overview, /Skill variety/);
    assert.match(overview, /Download PDF/);
    assert.match(overview, /Copy summary/);
    assert.match(overview, /Verified sources/);
    assert.match(overview, /Lecture13\.pdf/);

    const process = render(InfographicCard, { infographic: PROCESS, sources: SOURCES });
    assert.match(process, /Process flow/);
    assert.match(process, /Prepare the question/);
    assert.match(process, /Retrieve evidence/);
    assert.match(process, /Generate the answer/);
    assert.match(process, /infographic-arrow/);
    assert.match(process, /<ol class="infographic-process"/);

    const comparison = render(InfographicCard, { infographic: COMPARISON, sources: SOURCES });
    assert.match(comparison, /Comparison/);
    assert.match(comparison, /Job rotation/);
    assert.match(comparison, /Job enlargement/);
    assert.match(comparison, /Similarities/);
    assert.match(comparison, /Differences/);
    assert.match(comparison, /infographic-column/);
  });

  check('layout labels and reference mapping are deterministic', () => {
    assert.equal(infographicLayoutLabel('overview'), 'Concept overview');
    assert.equal(infographicLayoutLabel('process'), 'Process flow');
    assert.equal(infographicLayoutLabel('comparison'), 'Comparison');
    assert.equal(infographicLayoutLabel('unknown'), 'Educational infographic');
    const refs = referencedSources(OVERVIEW, SOURCES);
    assert.deepEqual(refs.map(ref => `${ref.id}:${ref.source.filename}:${ref.source.page}`), ['1:Lecture13.pdf:4']);
    assert.deepEqual(referencedSources({ ...OVERVIEW, source_ids: [2, 9] }, SOURCES).map(ref => ref.id), [2]);
  });

  check('normalization rejects invalid structure and filters unsafe content', () => {
    assert.equal(normalizeInfographic(null), null);
    assert.equal(normalizeInfographic({ ...OVERVIEW, layout: 'evil' }), null);
    assert.equal(normalizeInfographic({ ...OVERVIEW, sections: [] }), null);
    assert.equal(normalizeInfographic({ ...OVERVIEW, source_ids: [3] }, 2), null);
    assert.equal(normalizeInfographic({ ...OVERVIEW, source_ids: [] }), null);
    assert.equal(normalizeInfographic({ ...OVERVIEW, takeaways: ['only one'] }), null);
    const sanitized = normalizeInfographic({
      ...OVERVIEW,
      title: 'Job <script>alert(1)</script> Design',
      sections: [
        { heading: 'Task <b>scope</b>', body: '<script>alert(1)</script>Job design defines tasks and responsibilities.', icon: 'not-an-icon' },
        { heading: 'Skill variety', body: 'Job rotation develops employee skills across roles.', icon: 'workflow' }
      ],
      source_ids: [1, 1, 2, 2]
    }, 2);
    assert.equal(sanitized.title, 'Job Design');
    assert.equal(sanitized.sections[0].icon, 'sparkles');
    assert.equal(sanitized.sections[1].icon, 'workflow');
    assert.equal(sanitized.sections[0].heading, 'Task scope');
    assert.equal(sanitized.sections[0].body.includes('script'), false);
    assert.deepEqual(sanitized.source_ids, [1, 2]);
  });

  check('invalid saved output renders a safe fallback instead of markup', () => {
    const html = render(InfographicCard, { infographic: { title: '<img src=x onerror=alert(1)>', layout: 'grid' }, sources: SOURCES });
    assert.match(html, /could not be displayed safely/);
    assert.doesNotMatch(html, /<img/);
    assert.doesNotMatch(html, /onerror/);
  });

  check('copy summary text includes layout content and verified references', () => {
    const overview = infographicSummaryText(OVERVIEW, SOURCES);
    assert.match(overview, /Job Design Essentials/);
    assert.match(overview, /Concept overview/);
    assert.match(overview, /Task scope: Job design specifies/);
    assert.match(overview, /Definition: The process of organising work/);
    assert.match(overview, /Key takeaways/);
    assert.match(overview, /\[1\] Lecture13\.pdf, page 4/);
    const process = infographicSummaryText(PROCESS, SOURCES);
    assert.match(process, /1\. Prepare the question/);
    assert.match(process, /3\. Generate the answer/);
    const comparison = infographicSummaryText(COMPARISON, SOURCES);
    assert.match(comparison, /Job rotation: Moves between tasks; Builds broad skills/);
    assert.match(comparison, /Similarities/);
    assert.match(comparison, /Differences/);
    assert.equal(infographicSummaryText(null), '');
  });

  check('visible Generate Infographic action posts to the dedicated endpoint', () => {
    assert.match(source, /Generate Infographic/);
    assert.match(source, /infographic-button/);
    assert.match(source, /generateInfographic\(courseId, cleanQuestion, activeSession, requestId\)/);
    assert.match(apiSource, /\/chat\/infographic/);
    assert.match(source, /message\.role === 'infographic'/);
    assert.match(source, /<InfographicCard infographic=\{message\.infographic\}/);
    assert.match(styleSource, /\.infographic-card\s*\{/);
    assert.match(styleSource, /\.infographic-process\s*\{/);
    assert.match(styleSource, /\.infographic-compare\s*\{/);
    assert.match(styleSource, /@media print\s*\{/);
  });

  check('typed plain text is wrapped into an infographic request', () => {
    assert.equal(infographicPrompt(''), DEFAULT_INFOGRAPHIC_PROMPT);
    assert.equal(infographicPrompt('  Job Design  '), 'Make an infographic about: Job Design');
    assert.equal(infographicPrompt('Explain KV Cache visually.'), 'Explain KV Cache visually.');
    assert.equal(infographicPrompt('Make an infographic about RAG'), 'Make an infographic about RAG');
  });

  check('persisted history keeps infographic role and restores its structure', () => {
    const rows = [
      { role: 'student', text: 'Make an infographic about Job Design.' },
      { role: 'infographic', text: JSON.stringify(OVERVIEW), infographic: OVERVIEW, sources: SOURCES },
      { role: 'generated', text: 'A normal chat answer.' }
    ];
    const messages = displayMessages(rows);
    assert.deepEqual(messages.map(message => message.role), ['student', 'infographic', 'assistant']);
    assert.equal(messages[1].infographic.layout, 'overview');
    assert.equal(messages[1].sources.length, 2);
  });

  check('renderer never injects model-generated HTML', () => {
    for (const file of [cardSource, source]) {
      assert.doesNotMatch(file, /dangerouslySetInnerHTML/);
      assert.doesNotMatch(file, /eval\(/);
    }
    assert.doesNotMatch(cardSource, /<script/);
  });

  check('PDF filename is branded, stable and A4 safe', () => {
    assert.equal(
      infographicPdfFilename({ title: 'Job Design Essentials', exportedAt: new Date('2026-11-17T12:00:00Z') }),
      'knowledgepilot-infographic-job-design-essentials-2026-11-17.pdf'
    );
    assert.match(infographicPdfFilename({ title: '', exportedAt: new Date('2026-11-17T12:00:00Z') }), /knowledgepilot-infographic-study-topic-/);
  });

  const overviewBytes = buildPdf({ infographic: OVERVIEW, sources: SOURCES, courseName: 'PPIT', exportedAt: new Date('2026-11-17T12:00:00Z') });
  const processBytes = buildPdf({ infographic: PROCESS, sources: SOURCES, courseName: 'PPIT', exportedAt: new Date('2026-11-17T12:00:00Z') });
  const comparisonBytes = buildPdf({ infographic: COMPARISON, sources: SOURCES, courseName: 'PPIT', exportedAt: new Date('2026-11-17T12:00:00Z') });
  writeArtifact('overview.pdf', overviewBytes);
  writeArtifact('process.pdf', processBytes);
  writeArtifact('comparison.pdf', comparisonBytes);
  planFiles = [
    { name: 'overview.pdf', markers: ['Job Design Essentials', 'Concept Overview', 'Task scope', 'DEFINITION', 'KEY TAKEAWAYS', 'VERIFIED SOURCES', 'Lecture13.pdf'] },
    { name: 'process.pdf', markers: ['Grounded RAG Flow', 'Process Flow', 'Prepare the question', 'Generate the answer', 'KEY TAKEAWAYS', 'VERIFIED SOURCES'] },
    { name: 'comparison.pdf', markers: ['Job Rotation vs Job Enlargement', 'Comparison', 'Job rotation', 'Job enlargement', 'SIMILARITIES', 'DIFFERENCES', 'KEY TAKEAWAYS'] }
  ];

  check('long infographics paginate with page numbers', () => {
    const body = 'Job design defines tasks, responsibilities and relationships with clear evidence. '.repeat(8);
    const sections = Array.from({ length: 6 }, (_, index) => ({
      heading: `Concept ${index + 1}`,
      body,
      icon: 'layers',
      definition: 'A grounded definition drawn from the retrieved lecture page.',
      example: 'A grounded example drawn from the retrieved lecture page.'
    }));
    const long = { ...OVERVIEW, sections, takeaways: ['One grounded takeaway.', 'Two grounded takeaways.'] };
    const bytes = buildPdf({ infographic: long, sources: SOURCES, courseName: 'PPIT', exportedAt: new Date('2026-11-17T12:00:00Z') });
    const text = Buffer.from(bytes).toString('latin1');
    const pageCount = (text.match(/\/Type \/Page\b/g) || []).length;
    assert.ok(pageCount > 1, 'Long infographic should span multiple A4 pages');
    writeArtifact('long.pdf', bytes);
  });
} finally {
  await server.close();
}

const candidates = [
  resolve(here, '..', 'backend', '.venv', 'Scripts', 'python.exe'),
  resolve(here, '..', '.venv', 'Scripts', 'python.exe'),
  resolve(here, '..', 'backend', '.venv', 'bin', 'python')
];
const python = candidates.find(existsSync);
assert.ok(python, 'A backend Python interpreter with PyMuPDF must be available for PDF validation');
const script = [
  'import json, sys, pymupdf',
  'reports = []',
  'for path in sys.argv[1:]:',
  '    document = pymupdf.open(path)',
  '    text = "\\n".join(page.get_text() for page in document)',
  '    reports.append({"name": path, "pages": document.page_count, "text": text})',
  'print(json.dumps(reports))'
].join('\n');
const files = planFiles.map(report => resolve(artifacts, report.name));
const parsedResult = spawnSync(python, ['-c', script, ...files], { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 });
assert.equal(parsedResult.status, 0, parsedResult.stderr || 'PDF parser failed');
const parsed = JSON.parse(parsedResult.stdout);
const byName = Object.fromEntries(parsed.map(report => [basename(report.name), report]));

check('infographic PDFs open in a real parser with branding and references', () => {
  for (const plan of planFiles) {
    const open = byName[plan.name];
    assert.ok(open, `Parser did not open ${plan.name}`);
    assert.ok(open.pages >= 1);
    assert.match(open.text, /KnowledgePilot AI/);
    assert.match(open.text, /EDUCATIONAL INFOGRAPHIC/);
    assert.match(open.text, /Page 1 of \d+/);
    assert.match(open.text, /verify against the cited pages/);
    for (const marker of plan.markers) assert.ok(open.text.includes(marker), `${plan.name} is missing ${marker}`);
  }
});

rmSync(artifacts, { recursive: true, force: true });
console.log(`${passed} focused infographic checks passed.`);
