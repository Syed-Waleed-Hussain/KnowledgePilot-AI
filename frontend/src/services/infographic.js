/** Safe, dependency-free normalization for persisted infographic JSON. */

export const INFOGRAPHIC_LAYOUTS = ['overview', 'process', 'comparison'];
export const INFOGRAPHIC_ICONS = [
  'sparkles', 'layers', 'target', 'book', 'cpu', 'workflow', 'check',
  'lightbulb', 'git-branch', 'shield', 'database', 'brain', 'list',
  'refresh', 'settings', 'users', 'zap', 'search', 'file-text', 'scale',
  'boxes', 'compass', 'puzzle', 'clock', 'network', 'arrow-right'
];

const LAYOUT_LABELS = {
  overview: 'Concept overview',
  process: 'Process flow',
  comparison: 'Comparison'
};

export function plainText(value) {
  return String(value ?? '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function limit(value, maximum) {
  return plainText(value).slice(0, maximum).replace(/\s+$/, '');
}

function safeIcon(value) {
  const name = plainText(value).toLowerCase().replace(/_/g, '-');
  return INFOGRAPHIC_ICONS.includes(name) ? name : 'sparkles';
}

function safeArray(value, minimum, maximum, minimumLength, maximumLength) {
  if (!Array.isArray(value)) return [];
  const items = [];
  for (const entry of value.slice(0, maximum)) {
    const item = limit(entry, maximumLength);
    if (item.length >= minimumLength) items.push(item);
    if (items.length >= maximum) break;
  }
  return items.length >= minimum ? items : [];
}

function safeSections(value, maximum) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, maximum).map(item => {
    if (!item || typeof item !== 'object') return null;
    const heading = limit(item.heading || item.title, 80);
    const body = limit(item.body || item.detail || item.text, 400);
    if (heading.length < 2 || body.length < 8) return null;
    const section = { heading, body, icon: safeIcon(item.icon) };
    const definition = limit(item.definition, 300);
    const example = limit(item.example, 300);
    if (definition.length >= 5) section.definition = definition;
    if (example.length >= 5) section.example = example;
    return section;
  }).filter(Boolean);
}

function safeSteps(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 6).map(item => {
    if (!item || typeof item !== 'object') return null;
    const title = limit(item.title || item.heading, 80);
    const detail = limit(item.detail || item.body || item.text, 320);
    if (title.length < 2 || detail.length < 8) return null;
    return { title, detail, icon: safeIcon(item.icon) };
  }).filter(Boolean);
}

function safeColumns(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 4).map(item => {
    if (!item || typeof item !== 'object') return null;
    const title = limit(item.title || item.heading, 60);
    const points = safeArray(item.points, 2, 5, 4, 240);
    if (title.length < 2 || points.length < 2) return null;
    return { title, points };
  }).filter(Boolean);
}

function safeSourceIds(value, sourceCount) {
  if (!Array.isArray(value)) return [];
  const ids = [];
  for (const entry of value.slice(0, 8)) {
    const number = Number(entry);
    if (!Number.isInteger(number) || number < 1) continue;
    if (Number.isInteger(sourceCount) && sourceCount > 0 && number > sourceCount) continue;
    if (!ids.includes(number)) ids.push(number);
  }
  return ids;
}

export function normalizeInfographic(value, sourceCount = 0) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const layout = INFOGRAPHIC_LAYOUTS.includes(value.layout) ? value.layout : '';
  const title = limit(value.title, 140);
  const introduction = limit(value.introduction, 700);
  const takeaways = safeArray(value.takeaways, 2, 5, 5, 220);
  const sourceIds = safeSourceIds(value.source_ids, sourceCount);
  if (!layout || title.length < 3 || introduction.length < 20 || takeaways.length < 2 || !sourceIds.length) return null;

  const document = { title, layout, introduction, sections: [], steps: [], columns: [], similarities: [], differences: [], takeaways, source_ids: sourceIds };
  if (layout === 'overview') {
    document.sections = safeSections(value.sections, 6);
    if (document.sections.length < 2) return null;
  } else if (layout === 'process') {
    document.steps = safeSteps(value.steps);
    if (document.steps.length < 3) return null;
    document.sections = safeSections(value.sections, 3);
  } else {
    document.columns = safeColumns(value.columns);
    document.similarities = safeArray(value.similarities, 1, 4, 4, 240);
    document.differences = safeArray(value.differences, 1, 4, 4, 240);
    if (document.columns.length < 2 || !document.similarities.length || !document.differences.length) return null;
    document.sections = safeSections(value.sections, 3);
  }
  return document;
}

export function infographicLayoutLabel(layout) {
  return LAYOUT_LABELS[layout] || 'Educational infographic';
}

export function referencedSources(infographic, sources = []) {
  const ids = Array.isArray(infographic?.source_ids) ? infographic.source_ids : [];
  return ids.map(id => ({ id, source: sources[id - 1] })).filter(item => item.source);
}

export function infographicSummaryText(infographic, sources = []) {
  if (!infographic) return '';
  const lines = [infographic.title, infographicLayoutLabel(infographic.layout), '', infographic.introduction, ''];
  if (infographic.layout === 'overview') {
    lines.push('Concept cards');
    for (const section of infographic.sections) {
      lines.push(`- ${section.heading}: ${section.body}`);
      if (section.definition) lines.push(`  Definition: ${section.definition}`);
      if (section.example) lines.push(`  Example: ${section.example}`);
    }
  } else if (infographic.layout === 'process') {
    lines.push('Process steps');
    infographic.steps.forEach((step, index) => lines.push(`${index + 1}. ${step.title}: ${step.detail}`));
    if (infographic.sections.length) {
      lines.push('', 'Key concepts');
      for (const section of infographic.sections) lines.push(`- ${section.heading}: ${section.body}`);
    }
  } else {
    lines.push('Comparison');
    for (const column of infographic.columns) lines.push(`- ${column.title}: ${column.points.join('; ')}`);
    lines.push('', 'Similarities', ...infographic.similarities.map(item => `- ${item}`));
    lines.push('', 'Differences', ...infographic.differences.map(item => `- ${item}`));
  }
  lines.push('', 'Key takeaways', ...infographic.takeaways.map(item => `- ${item}`));
  const references = referencedSources(infographic, sources);
  if (references.length) {
    lines.push('', 'Verified sources');
    for (const { id, source } of references) lines.push(`[${id}] ${source.filename}, page ${source.page}`);
  }
  return lines.join('\n').trim();
}
