import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const here = dirname(fileURLToPath(import.meta.url));
const artifacts = resolve(here, '.pdf-test-artifacts');
rmSync(artifacts, { recursive: true, force: true });
mkdirSync(artifacts, { recursive: true });

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
let passed = 0;
function check(name, callback) { callback(); passed += 1; console.log('PASS', name); }
async function checkAsync(name, callback) { await callback(); passed += 1; console.log('PASS', name); }
function render(Component, props) { return renderToStaticMarkup(React.createElement(Component, props)); }
function buttonTag(html, label) {
  const index = html.indexOf(label);
  assert.notEqual(index, -1, `Expected a ${label} button`);
  return html.slice(html.lastIndexOf('<button', index), index);
}
function buildReport(options) {
  const bytes = buildResearchPdf(options);
  const text = Buffer.from(bytes).toString('latin1');
  assert.ok(text.startsWith('%PDF-1.4'), 'PDF signature is missing');
  assert.match(text, /%%EOF\s*$/, 'PDF end marker is missing');
  return bytes;
}
function writeArtifact(name, bytes) { return writeFileSync(resolve(artifacts, name), bytes); }

const summary = `## Key findings

Hybrid retrieval improved recall by 12% [1]. **Bold evidence** and *careful caveats* are both retained.

| Measure | Baseline | Hybrid |
| --- | --- | --- |
| Recall | 71% | 83% |
| Latency | 120 ms | 135 ms |

### Implications

- Retrieval practice may help revision.
- Larger samples are still needed.

## References

1. Synthetic Author. 2026. Synthetic Sensor Study. https://arxiv.org/abs/2601.12345 DOI: 10.1234/synthetic
`;
const review = `## Major themes

Evidence remains mixed across the reviewed studies [2]. RANDOM_REVIEW_SENTINEL

## References

2. Review Author. 2025. Review Paper. https://arxiv.org/abs/2601.54321
`;
const comparison = `## Comparison

| Study | Design | Sample |
| --- | --- | --- |
| Synthetic Sensor Study | Experiment | 120 |
| Review Paper | Survey | 48 |

### Recommendation

Start with the experiment, then verify against the survey.`;
const savedSummary = '## Saved summary\n\nSAVED_SUMMARY_SENTINEL from a previously stored draft.';
const outputs = [
  { id: 'out-review', task: 'review', answer: review, created_at: '2026-11-17 10:00:00' },
  { id: 'out-compare', task: 'compare', answer: comparison, created_at: '2026-11-16 09:00:00' },
  { id: 'out-summary', task: 'summary', answer: savedSummary, created_at: '2026-11-15 08:00:00' }
];

let ResearchOutput, outputForTab, reportTypeFor, pdfFilename, buildResearchPdf, downloadResearchPdf, copyDraftText, __pdfInternals;
try {
  ({ ResearchOutput, outputForTab } = await server.ssrLoadModule('/src/pages/Research.jsx'));
  ({ reportTypeFor, pdfFilename, buildResearchPdf, downloadResearchPdf, copyDraftText, __pdfInternals } = await server.ssrLoadModule('/src/services/researchPdf.js'));
  const source = readFileSync(resolve(here, 'src/pages/Research.jsx'), 'utf8');
  const pdfSource = readFileSync(resolve(here, 'src/services/researchPdf.js'), 'utf8');
  const generated = { task: 'summary', answer: summary, created_at: '2026-11-17 11:00:00' };
  const savedReports = [];

  check('PDF action is visible when a generated draft exists', () => {
    const html = render(ResearchOutput, { output: summary, outputTask: 'summary', outputTab: 'summary' });
    assert.match(html, /Download PDF/);
    assert.match(html, /Copy text/);
    assert.match(html, /Download Markdown/);
    assert.doesNotMatch(buttonTag(html, 'Download PDF'), /disabled/);
    assert.match(source, /onClick=\{\(\)=>onDownloadPdf\(visible\)\}/);
    assert.match(source, /exportDraft\(visible,'pdf'\)/);
  });

  check('export controls are disabled when no draft exists', () => {
    const html = render(ResearchOutput, { outputTab: 'summary' });
    for (const label of ['Download PDF', 'Copy text', 'Download Markdown']) {
      assert.match(buttonTag(html, label), /disabled/);
    }
    const notes = render(ResearchOutput, {
      outputTab: 'notes',
      notesView: React.createElement('section', null, 'Private note panel')
    });
    assert.doesNotMatch(notes, /Download PDF/);
    assert.doesNotMatch(notes, /Download Markdown/);
    assert.match(notes, /Private note panel/);
  });

  check('the currently displayed generated draft is the export source', () => {
    const visible = outputForTab({ tab: 'summary', output: summary, outputTask: 'summary', outputs, savedId: '' });
    assert.equal(visible.saved, false);
    assert.equal(visible.answer, summary);
    const bytes = buildReport({ answer: visible.answer, task: visible.task, topicTitle: 'Active draft topic' });
    const metadata = { name: 'generated-summary.pdf', bytes, marker: 'Hybrid retrieval improved recall' };
    savedReports.push(metadata);
    writeArtifact(metadata.name, bytes);
    assert.notEqual(outputForTab({ tab: 'review', output: summary, outputTask: 'summary', outputs }).answer, summary);
  });

  check('a selected saved draft is exported instead of an older draft', () => {
    const visible = outputForTab({ tab: 'saved', outputs, savedId: 'out-summary' });
    assert.equal(visible.saved, true);
    assert.equal(visible.id, 'out-summary');
    assert.match(visible.answer, /SAVED_SUMMARY_SENTINEL/);
    const bytes = buildReport({ answer: visible.answer, task: visible.task, topicTitle: 'Saved draft topic' });
    savedReports.push({ name: 'saved-summary.pdf', bytes, marker: 'SAVED_SUMMARY_SENTINEL' });
    writeArtifact('saved-summary.pdf', bytes);
    assert.equal(outputForTab({ tab: 'saved', outputs, savedId: 'missing' }), null);
  });

  check('summary reports use the Paper Summary report type', () => {
    assert.equal(reportTypeFor('summary'), 'Paper Summary');
    const bytes = buildReport({ answer: summary, task: 'summary', topicTitle: 'Summary Topic' });
    savedReports.push({ name: 'summary-type.pdf', bytes, marker: 'Paper Summary' });
    writeArtifact('summary-type.pdf', bytes);
  });

  check('literature reviews use the Literature Review report type', () => {
    assert.equal(reportTypeFor('review'), 'Literature Review');
    const bytes = buildReport({ answer: review, task: 'review', topicTitle: 'Review Topic' });
    savedReports.push({ name: 'review-type.pdf', bytes, marker: 'Literature Review' });
    writeArtifact('review-type.pdf', bytes);
  });

  check('comparison drafts use the Paper Comparison report type', () => {
    assert.equal(reportTypeFor('compare'), 'Paper Comparison');
    const bytes = buildReport({ answer: comparison, task: 'compare', topicTitle: 'Comparison Topic' });
    savedReports.push({ name: 'comparison-type.pdf', bytes, marker: 'Paper Comparison' });
    writeArtifact('comparison-type.pdf', bytes);
  });

  check('Markdown headings, tables, lists and inline emphasis are parsed safely', () => {
    const blocks = __pdfInternals.parseMarkdown(summary);
    assert.deepEqual(blocks.map(block => block.type), ['heading', 'paragraph', 'table', 'heading', 'list', 'heading', 'list']);
    assert.deepEqual(blocks[2].rows[0], ['Measure', 'Baseline', 'Hybrid']);
    assert.deepEqual(blocks[2].rows[1], ['Recall', '71%', '83%']);
    const spans = __pdfInternals.inlineSpans('**Strong** and *soft* and [source](https://arxiv.org/abs/2601.12345)');
    assert.ok(spans.some(span => span.text === 'Strong' && span.font === 'F2'));
    assert.ok(spans.some(span => span.text === 'soft' && span.font === 'F3'));
    assert.ok(spans.some(span => span.text === 'source' && span.link === 'https://arxiv.org/abs/2601.12345'));
    const text = Buffer.from(buildResearchPdf({ answer: summary, task: 'summary', topicTitle: 'Markdown Topic' })).toString('latin1');
    assert.match(text, /\(Key\) Tj/);
    assert.match(text, /\(Recall\) Tj/);
    assert.match(text, /\(83%\) Tj/);
  });

  check('untrusted HTML and unsafe links are not executed or linked', () => {
    const untrusted = `## Untrusted content\n\n<script>alert('xss')</script>\n<img src=x onerror="alert(1)">\n[bad link](javascript:alert(1))\n[good link](https://example.org/paper)\n`;
    const spans = __pdfInternals.inlineSpans(untrusted.split('\n')[4]);
    assert.equal(spans.some(span => span.link), false);
    assert.equal(__pdfInternals.safeUrl('javascript:alert(1)'), null);
    const bytes = buildReport({ answer: untrusted, task: 'summary', topicTitle: 'Untrusted Topic' });
    const text = Buffer.from(bytes).toString('latin1');
    assert.doesNotMatch(text, /<script|onerror|javascript:/i);
    savedReports.push({ name: 'untrusted.pdf', bytes, marker: 'Untrusted content', forbidden: ['javascript:', '<script', 'onerror'] });
    writeArtifact('untrusted.pdf', bytes);
  });

  check('verified paper references, titles, authors, DOIs and URLs are preserved', () => {
    const bytes = buildReport({ answer: summary, task: 'summary', topicTitle: 'References Topic' });
    const text = Buffer.from(bytes).toString('latin1');
    assert.match(text, /\(Synthetic\) Tj/);
    assert.match(text, /\(Author\.\) Tj/);
    assert.match(text, /\(Sensor\) Tj/);
    assert.match(text, /\(Study\.\) Tj/);
    assert.match(text, /10\.1234\/synthetic/);
    assert.match(text, /https:\/\/arxiv\.org\/abs\/2601\.12345/);
    savedReports.push({ name: 'references.pdf', bytes, marker: '10.1234/synthetic', links: ['https://arxiv.org/abs/2601.12345'] });
    writeArtifact('references.pdf', bytes);
  });

  check('authentication tokens, session data and internal paths are not exported', () => {
    const bytes = buildReport({ answer: summary, task: 'summary', topicTitle: 'Safe Export Topic' });
    const text = Buffer.from(bytes).toString('latin1');
    for (const forbidden of ['access_token', 'refresh_token', 'Bearer ', 'eyJhbGciOi', 'storage_phase3', 'courses.sqlite3', 'backend\\', 'C:\\']) {
      assert.equal(text.includes(forbidden), false, `Unexpected secret or internal path: ${forbidden}`);
    }
    assert.doesNotMatch(pdfSource, /access_token|refresh_token|localStorage|sessionStorage|Authorization/i);
  });

  check('the browser download helper emits a named application/pdf blob', () => {
    const clicks = [];
    const blobs = [];
    globalThis.Blob = class {
      constructor(parts, options) { this.parts = parts; this.type = options?.type; blobs.push(this); }
    };
    globalThis.URL.createObjectURL = blob => { assert.equal(blob.type, 'application/pdf'); return 'blob:pdf-test'; };
    globalThis.URL.revokeObjectURL = () => {};
    const link = { href: '', download: '', click() { clicks.push({ href: this.href, download: this.download }); }, remove() {} };
    globalThis.document = { createElement: () => link, body: { appendChild() {} } };
    const filename = downloadResearchPdf({ answer: '## Browser draft\n\nDownload helper marker.', task: 'review', topicTitle: 'Browser Test', exportedAt: new Date('2026-11-17T00:00:00Z') });
    assert.equal(filename, 'knowledgepilot-literature-review-browser-test-2026-11-17.pdf');
    assert.equal(link.download, filename);
    assert.equal(link.href, 'blob:pdf-test');
    assert.equal(clicks.length, 1);
    assert.equal(blobs.length, 1);
    assert.equal(blobs[0].type, 'application/pdf');
    assert.ok(Buffer.from(blobs[0].parts[0]).toString('latin1').startsWith('%PDF-1.4'));
  });

  await checkAsync('the Copy text helper writes the visible draft to the clipboard', async () => {
    let copied = '';
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      writable: true,
      value: { clipboard: { writeText: async value => { copied = value; } } }
    });
    await copyDraftText(summary);
    assert.equal(copied, summary);
    await assert.rejects(copyDraftText(''), /No draft text is available to copy/);
  });

  check('long reports paginate with page numbers and no content overlap', () => {
    const paragraph = 'This paragraph contains a detailed discussion of evidence quality and the limits of the reviewed studies. '.repeat(10);
    const long = Array.from({ length: 7 }, (_, index) => `## Section ${index + 1}\n\n${paragraph}\n\n- Finding ${index + 1}\n- Caveat ${index + 1}\n`).join('\n');
    const bytes = buildReport({ answer: long, task: 'review', topicTitle: 'A Very Long Research Topic Title That Should Wrap Across Multiple Lines And Still Look Professional' });
    savedReports.push({ name: 'long-report.pdf', bytes, marker: 'Section 7', paginated: true });
    writeArtifact('long-report.pdf', bytes);
  });

  check('existing Generated Output and My Notes tabs remain functional', () => {
    const html = render(ResearchOutput, {
      output: summary,
      outputTask: 'summary',
      outputTab: 'summary',
      outputs,
      notesView: React.createElement('section', null, 'My Notes content'),
      onDownloadPdf: () => {},
      onCopyText: () => {},
      onDownloadMarkdown: () => {}
    });
    for (const label of ['Summary', 'Literature Review', 'Saved outputs', 'My Notes']) assert.match(html, new RegExp(label));
    assert.match(html, /GENERATED OUTPUT/);
    assert.match(html, /Key findings/);
    const notes = render(ResearchOutput, { outputTab: 'notes', notesView: React.createElement('section', null, 'My Notes content') });
    assert.match(notes, /PRIVATE NOTES/);
    assert.match(notes, /My Notes content/);
    assert.equal(pdfFilename({ task: 'review', topicTitle: 'Agentic Retrieval Systems', exportedAt: new Date('2026-11-17T12:00:00Z') }), 'knowledgepilot-literature-review-agentic-retrieval-systems-2026-11-17.pdf');
  });

  // Open every generated report with the existing backend PDF parser.
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
    '    links = [link.get("uri") for page in document for link in page.get_links() if link.get("uri")]',
    '    reports.append({"name": path, "pages": document.page_count, "text": text, "links": links})',
    'print(json.dumps(reports))'
  ].join('\n');
  const files = savedReports.map(report => resolve(artifacts, report.name));
  const parsedResult = spawnSync(python, ['-c', script, ...files], { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 });
  assert.equal(parsedResult.status, 0, parsedResult.stderr || 'PDF parser failed');
  const parsed = JSON.parse(parsedResult.stdout);
  assert.equal(parsed.length, savedReports.length);
  const byName = Object.fromEntries(parsed.map(report => [basename(report.name), report]));

  check('generated PDF files open in a real parser with expected text and links', () => {
    for (const report of savedReports) {
      const open = byName[report.name];
      assert.ok(open, `Parser did not open ${report.name}`);
      assert.ok(open.pages >= 1);
      assert.match(open.text, /KnowledgePilot AI/);
      assert.match(open.text, /Page 1 of \d+/);
      assert.match(open.text, /AI-generated research draft/);
      if (report.marker) assert.ok(open.text.includes(report.marker), `${report.name} is missing ${report.marker}`);
      for (const forbidden of report.forbidden || []) assert.equal(open.text.includes(forbidden), false);
      for (const link of report.links || []) assert.ok(open.links.includes(link), `${report.name} is missing link ${link}`);
    }
    assert.ok(byName['summary-type.pdf'].text.includes('Paper Summary'));
    assert.ok(byName['review-type.pdf'].text.includes('Literature Review'));
    assert.ok(byName['comparison-type.pdf'].text.includes('Paper Comparison'));
    assert.ok(byName['generated-summary.pdf'].text.includes('Recall'));
    assert.ok(byName['generated-summary.pdf'].text.includes('83%'));
    assert.equal(byName['untrusted.pdf'].links.some(link => link.startsWith('javascript:')), false);
    assert.ok(byName['untrusted.pdf'].links.includes('https://example.org/paper'));
    const long = byName['long-report.pdf'];
    assert.ok(long.pages > 1, 'Long report should span multiple A4 pages');
    for (let page = 1; page <= long.pages; page += 1) assert.ok(long.text.includes(`Page ${page} of ${long.pages}`));
  });

  console.log(`${passed} focused PDF export checks passed.`);
  rmSync(artifacts, { recursive: true, force: true });
} finally {
  await server.close();
}
