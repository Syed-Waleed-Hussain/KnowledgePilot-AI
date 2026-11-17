/**
 * Dependency-free A4 research report PDF writer.
 * Produces a real PDF (standard fonts, link annotations, page numbers) from safe Markdown text.
 * No HTML is injected and no authentication/session data is accepted or emitted.
 */

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN = 48;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;
const BOTTOM = PAGE_HEIGHT - 92;
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const COLORS = {
  violet: [0.29, 0.16, 0.52],
  lavender: [0.55, 0.44, 0.72],
  lightViolet: [0.955, 0.94, 0.985],
  blue: [0.16, 0.39, 0.85],
  ink: [0.14, 0.12, 0.18],
  muted: [0.42, 0.39, 0.48],
  border: [0.85, 0.81, 0.90],
  white: [1, 1, 1],
  softBlue: [0.94, 0.96, 1]
};

const REPORT_TYPES = {
  summary: 'Paper Summary',
  review: 'Literature Review',
  compare: 'Paper Comparison'
};

const INFOGRAPHIC_LAYOUTS = {
  overview: 'Concept Overview',
  process: 'Process Flow',
  comparison: 'Comparison'
};

const INFOGRAPHIC_ACCENTS = [
  [0.29, 0.16, 0.52],
  [0.16, 0.39, 0.85],
  [0.45, 0.29, 0.66],
  [0.13, 0.47, 0.52]
];

export function reportTypeFor(task) {
  return REPORT_TYPES[task] || 'Research Report';
}

function normalizeText(value) {
  return String(value ?? '')
    .replace(/\u2018|\u2019/g, "'")
    .replace(/\u201c|\u201d/g, '"')
    .replace(/\u2013|\u2014/g, '-')
    .replace(/\u2026/g, '...')
    .replace(/\u2022|\u25cf/g, '-')
    .replace(/\u00a0/g, ' ')
    .replace(/\u2192/g, '->')
    .replace(/\u2190/g, '<-')
    .replace(/\u2191/g, '^')
    .replace(/\u2193/g, 'v')
    .replace(/\u2248/g, '~')
    .replace(/\u2260/g, '!=')
    .replace(/\u2265/g, '>=')
    .replace(/\u2264/g, '<=')
    .replace(/\u00d7/g, 'x')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '')
    .replace(/[^\x20-\x7e\xa0-\xff]/g, '');
}

function pdfString(value) {
  return normalizeText(value).replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)').replace(/\r?\n/g, ' ');
}

function charWidth(character, font) {
  const bold = font === 'F2' || font === 'F4';
  if (character === ' ') return 278;
  if ('ilIjtfr.,:;!|\'`'.includes(character)) return bold ? 278 : 222;
  if ('mwMW'.includes(character)) return bold ? 833 : 722;
  if (character >= 'A' && character <= 'Z') return bold ? 722 : 667;
  if (character >= 'a' && character <= 'z') return 556;
  if (character >= '0' && character <= '9') return 556;
  if (character === '@') return 1015;
  if ('%&'.includes(character)) return 889;
  if ('-+='.includes(character)) return 584;
  if ('()[]{}'.includes(character)) return 333;
  return 500;
}

function textWidth(value, font = 'F1', size = 10) {
  let width = 0;
  for (const character of normalizeText(value)) width += charWidth(character, font);
  return (width / 1000) * size;
}

function formatExportDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

function isoDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return 'undated';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function slug(value) {
  return normalizeText(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

export function pdfFilename({ task, topicTitle, exportedAt = new Date() }) {
  const type = slug(reportTypeFor(task)) || 'research-report';
  const topic = slug(topicTitle).slice(0, 52) || 'research-topic';
  return `knowledgepilot-${type}-${topic}-${isoDate(exportedAt)}.pdf`;
}

function safeUrl(value) {
  const candidate = String(value || '').trim();
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) ? candidate : null;
  } catch {
    return null;
  }
}

function sanitizeInline(value) {
  return String(value ?? '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\\([\\`*_{}\[\]()~!>#+\-.])/g, '$1');
}

const INLINE_PATTERN = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|(?<![A-Za-z0-9])__([^_]+)__(?![A-Za-z0-9])|`([^`]+)`|\*([^*\n]+)\*|(?<![A-Za-z0-9])_([^_\n]+)_(?![A-Za-z0-9])|(https?:\/\/[^\s<)]+)/g;

function pushSpan(spans, span) {
  const previous = spans[spans.length - 1];
  if (previous && previous.font === span.font && previous.color === span.color && previous.link === span.link) previous.text += span.text;
  else spans.push({ ...span });
}

function inlineSpans(value) {
  const source = sanitizeInline(value);
  const spans = [];
  let last = 0;
  INLINE_PATTERN.lastIndex = 0;
  let match;
  while ((match = INLINE_PATTERN.exec(source))) {
    if (match.index > last) pushSpan(spans, { text: source.slice(last, match.index) });
    if (match[1]) {
      const url = safeUrl(match[2]);
      pushSpan(spans, url ? { text: match[1], link: url, color: COLORS.blue } : { text: match[1] });
    } else if (match[3] || match[4]) pushSpan(spans, { text: match[3] || match[4], font: 'F2' });
    else if (match[5]) pushSpan(spans, { text: match[5], font: 'F5' });
    else if (match[6] || match[7]) pushSpan(spans, { text: match[6] || match[7], font: 'F3' });
    else if (match[8]) {
      const url = safeUrl(match[8]);
      pushSpan(spans, url ? { text: match[8], link: url, color: COLORS.blue } : { text: match[8] });
    }
    last = INLINE_PATTERN.lastIndex;
  }
  if (last < source.length) pushSpan(spans, { text: source.slice(last) });
  return spans;
}

function plainInline(value) {
  return inlineSpans(value).map(span => span.text).join('').replace(/\s+/g, ' ').trim();
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
}

function startsBlock(lines, index) {
  const line = lines[index] || '';
  return /^\s*$/.test(line)
    || /^(#{1,6})\s+/.test(line)
    || /^\s*```/.test(line)
    || /^\s*>/.test(line)
    || /^\s*(?:---|\*\*\*|___)\s*$/.test(line)
    || /^(\s*)([-*+]|\d+[.)])\s+/.test(line)
    || (line.includes('|') && isTableSeparator(lines[index + 1] || ''));
}

function parseMarkdown(markdown) {
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (/^\s*$/.test(line)) { index += 1; continue; }
    if (/^\s*```/.test(line)) {
      const code = [];
      index += 1;
      while (index < lines.length && !/^\s*```/.test(lines[index])) code.push(lines[index++]);
      index += 1;
      blocks.push({ type: 'code', text: code.join('\n') });
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }
    if (/^\s*(?:---|\*\*\*|___)\s*$/.test(line)) { blocks.push({ type: 'rule' }); index += 1; continue; }
    if (line.includes('|') && isTableSeparator(lines[index + 1] || '')) {
      const rows = [splitTableRow(line)];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && !/^\s*$/.test(lines[index])) rows.push(splitTableRow(lines[index++]));
      blocks.push({ type: 'table', rows });
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quote = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) quote.push(lines[index++].replace(/^\s*>\s?/, ''));
      blocks.push({ type: 'quote', text: quote.join(' ') });
      continue;
    }
    const item = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (item) {
      const items = [];
      while (index < lines.length) {
        const match = lines[index].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (!match) break;
        items.push({ indent: match[1].length, ordered: /\d/.test(match[2]), text: match[3] });
        index += 1;
      }
      blocks.push({ type: 'list', items });
      continue;
    }
    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && !startsBlock(lines, index)) paragraph.push(lines[index++].trim());
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
  }
  return blocks;
}

function tokenize(spans, size) {
  const units = [];
  for (const span of spans) {
    const font = span.font || 'F1';
    for (const word of normalizeText(span.text).split(/\s+/).filter(Boolean)) {
      units.push({ ...span, font, text: word, width: textWidth(word, font, size) });
    }
  }
  return units;
}

function splitLongUnit(unit, maxWidth, size) {
  const pieces = [];
  let piece = '';
  for (const character of unit.text) {
    const candidate = piece + character;
    if (piece && textWidth(candidate, unit.font, size) > maxWidth) {
      pieces.push(piece);
      piece = character;
    } else piece = candidate;
  }
  if (piece) pieces.push(piece);
  return pieces.map(text => ({ ...unit, text, width: textWidth(text, unit.font, size) }));
}

function wrapUnits(units, maxWidth, size) {
  const lines = [];
  let line = [];
  let width = 0;
  const spaceWidth = textWidth(' ', 'F1', size);
  const flush = () => { if (line.length) { lines.push(line); line = []; width = 0; } };
  for (const unit of units) {
    const candidates = unit.width > maxWidth ? splitLongUnit(unit, maxWidth, size) : [unit];
    for (const candidate of candidates) {
      const extra = line.length ? spaceWidth : 0;
      if (line.length && width + extra + candidate.width > maxWidth) flush();
      const nextExtra = line.length ? spaceWidth : 0;
      line.push(candidate);
      width += nextExtra + candidate.width;
    }
  }
  flush();
  return lines;
}

class PdfReport {
  constructor({ task, topicTitle, exportedAt, mode = 'research', courseName = '', layout = '' }) {
    this.task = task;
    this.topicTitle = topicTitle || 'Research topic';
    this.exportedAt = exportedAt;
    this.mode = mode;
    this.courseName = courseName;
    this.layout = layout;
    this.pages = [];
    this.page = null;
    this.y = 0;
    this.bottom = BOTTOM;
    this.inReferences = false;
    this.firstParagraph = true;
    this.newPage(true);
  }

  op(value) { this.page.ops.push(value); }

  newPage(first = false) {
    this.page = { ops: [], links: [] };
    this.pages.push(this.page);
    this.drawHeader(first);
  }

  ensureSpace(height) {
    if (this.y + height > this.bottom) this.newPage(false);
  }

  fillColor(color) { this.op(`${color.join(' ')} rg`); }
  strokeColor(color) { this.op(`${color.join(' ')} RG`); }

  rect(x, top, width, height, { fill, stroke, lineWidth = 0.6 } = {}) {
    const bottom = PAGE_HEIGHT - top - height;
    if (fill) this.op(`${fill.join(' ')} rg ${x.toFixed(2)} ${bottom.toFixed(2)} ${width.toFixed(2)} ${height.toFixed(2)} re f`);
    if (stroke) this.op(`${lineWidth} w ${stroke.join(' ')} RG ${x.toFixed(2)} ${bottom.toFixed(2)} ${width.toFixed(2)} ${height.toFixed(2)} re S`);
  }

  circle(x, top, radius, color) {
    const bottom = PAGE_HEIGHT - top;
    const k = 0.5523 * radius;
    this.op(`${color.join(' ')} rg ${(x + radius).toFixed(2)} ${bottom.toFixed(2)} m`);
    this.op(`${(x + radius).toFixed(2)} ${(bottom + k).toFixed(2)} ${(x + k).toFixed(2)} ${(bottom + radius).toFixed(2)} ${x.toFixed(2)} ${(bottom + radius).toFixed(2)} c`);
    this.op(`${(x - k).toFixed(2)} ${(bottom + radius).toFixed(2)} ${(x - radius).toFixed(2)} ${(bottom + k).toFixed(2)} ${(x - radius).toFixed(2)} ${bottom.toFixed(2)} c`);
    this.op(`${(x - radius).toFixed(2)} ${(bottom - k).toFixed(2)} ${(x - k).toFixed(2)} ${(bottom - radius).toFixed(2)} ${x.toFixed(2)} ${(bottom - radius).toFixed(2)} c`);
    this.op(`${(x + k).toFixed(2)} ${(bottom - radius).toFixed(2)} ${(x + radius).toFixed(2)} ${(bottom - k).toFixed(2)} ${(x + radius).toFixed(2)} ${bottom.toFixed(2)} c f`);
  }

  line(x1, top1, x2, top2, color = COLORS.border, width = 0.7) {
    this.op(`${width} w ${color.join(' ')} RG ${x1.toFixed(2)} ${(PAGE_HEIGHT - top1).toFixed(2)} m ${x2.toFixed(2)} ${(PAGE_HEIGHT - top2).toFixed(2)} l S`);
  }

  text(value, x, top, { font = 'F1', size = 10, color = COLORS.ink } = {}) {
    const clean = normalizeText(value);
    if (!clean) return 0;
    this.op(`BT /${font} ${size} Tf ${color.join(' ')} rg 1 0 0 1 ${x.toFixed(2)} ${(PAGE_HEIGHT - top).toFixed(2)} Tm (${pdfString(clean)}) Tj ET`);
    return textWidth(clean, font, size);
  }

  linkRect(url, x, top, width, size) {
    const baseline = PAGE_HEIGHT - top;
    this.page.links.push({ url, rect: [x, baseline - size * 0.22, x + width, baseline + size * 0.82] });
  }

  drawUnitLine(units, x, top, { size = 10.5, font = 'F1', color = COLORS.ink } = {}) {
    let cursor = x;
    const spaceWidth = textWidth(' ', font, size);
    for (let index = 0; index < units.length; index += 1) {
      const unit = units[index];
      const width = this.text(unit.text, cursor, top, { font: unit.font || font, size, color: unit.link ? COLORS.blue : (unit.color || color) });
      if (unit.link) this.linkRect(unit.link, cursor, top, width, size);
      cursor += width;
      if (index < units.length - 1) {
        this.text(' ', cursor, top, { font, size, color });
        cursor += spaceWidth;
      }
    }
    return cursor;
  }

  drawHeader(first) {
    if (this.mode === 'infographic') {
      this.drawInfographicHeader(first);
      return;
    }
    if (first) {
      this.rect(0, 0, PAGE_WIDTH, 8, { fill: COLORS.violet });
      this.text('KnowledgePilot AI', MARGIN, 45, { font: 'F2', size: 17, color: COLORS.violet });
      this.text('RESEARCH ENVIRONMENT', MARGIN, 61, { font: 'F1', size: 8.2, color: COLORS.lavender });
      const type = reportTypeFor(this.task);
      const badgeWidth = textWidth(type, 'F2', 8.2) + 22;
      this.rect(PAGE_WIDTH - MARGIN - badgeWidth, 32, badgeWidth, 18, { fill: COLORS.violet });
      this.text(type, PAGE_WIDTH - MARGIN - badgeWidth + 11, 45, { font: 'F2', size: 8.2, color: COLORS.white });
      this.line(MARGIN, 88, PAGE_WIDTH - MARGIN, 88, COLORS.border, 0.8);
      this.text('RESEARCH REPORT', MARGIN, 122, { font: 'F2', size: 8.5, color: COLORS.lavender });
      const titleLines = this.wrapPlain(this.topicTitle, 'F2', 22, CONTENT_WIDTH, 2);
      let titleTop = 152;
      for (const titleLine of titleLines) {
        this.text(titleLine, MARGIN, titleTop, { font: 'F2', size: 22, color: COLORS.violet });
        titleTop += 28;
      }
      this.text(`Exported ${formatExportDate(this.exportedAt)}  |  ${type}`, MARGIN, titleTop + 6, { font: 'F1', size: 9.6, color: COLORS.muted });
      const infoTop = titleTop + 20;
      this.rect(MARGIN, infoTop, CONTENT_WIDTH, 30, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
      this.text('AI-generated research draft - verify all claims against the original sources.', MARGIN + 12, infoTop + 19, { font: 'F1', size: 8.9, color: COLORS.muted });
      this.line(MARGIN, infoTop + 42, PAGE_WIDTH - MARGIN, infoTop + 42, COLORS.border, 0.6);
      this.y = infoTop + 66;
    } else {
      this.rect(0, 0, PAGE_WIDTH, 4, { fill: COLORS.violet });
      this.text('KnowledgePilot AI', MARGIN, 34, { font: 'F2', size: 10.5, color: COLORS.violet });
      this.text('Research Environment', MARGIN, 46, { font: 'F1', size: 7.8, color: COLORS.lavender });
      const type = reportTypeFor(this.task);
      this.text(type, PAGE_WIDTH - MARGIN - textWidth(type, 'F2', 8), 38, { font: 'F2', size: 8, color: COLORS.violet });
      this.line(MARGIN, 55, PAGE_WIDTH - MARGIN, 55, COLORS.border, 0.6);
      this.y = 82;
    }
  }

  wrapPlain(value, font, size, maxWidth, maxLines) {
    const words = normalizeText(value).split(/\s+/).filter(Boolean);
    const lines = [];
    let line = '';
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (line && textWidth(candidate, font, size) > maxWidth) {
        lines.push(line);
        line = word;
      } else line = candidate;
    }
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      const kept = lines.slice(0, maxLines);
      kept[kept.length - 1] = `${kept[kept.length - 1].replace(/\s+\S*$/, '')}...`;
      return kept;
    }
    return lines;
  }

  drawRich(spans, { size = 10.5, lineHeight = 15.2, indent = 0, maxWidth = CONTENT_WIDTH, color = COLORS.ink, spaceBefore = 0, spaceAfter = 8, font = 'F1' } = {}) {
    this.y += spaceBefore;
    const units = tokenize(spans, size);
    if (!units.length) { this.y += spaceAfter; return; }
    const lines = wrapUnits(units, maxWidth, size);
    let first = true;
    for (const line of lines) {
      if (this.y + lineHeight > this.bottom) this.newPage(false);
      this.drawUnitLine(line, MARGIN + indent, this.y, { size, font, color });
      this.y += lineHeight;
      first = false;
    }
    if (first) this.y += lineHeight;
    this.y += spaceAfter;
  }

  drawHeading(level, value) {
    const text = plainInline(value);
    if (!text) return;
    const keyFindings = /key findings/i.test(text) && level <= 3;
    const spaceBefore = level === 1 ? 16 : level === 2 ? 13 : 9;
    const size = level === 1 ? 18 : level === 2 ? 14 : level === 3 ? 11.5 : 10.5;
    const lineHeight = size * 1.35;
    this.y += spaceBefore;
    this.ensureSpace(lineHeight + (level <= 2 ? 18 : 8));
    if (keyFindings) {
      this.rect(MARGIN, this.y - lineHeight + 4, CONTENT_WIDTH, lineHeight + 8, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
      this.rect(MARGIN, this.y - lineHeight + 4, 4, lineHeight + 8, { fill: COLORS.violet });
      const lines = wrapUnits(tokenize([{ text, font: 'F2' }], 13), CONTENT_WIDTH - 24, 13);
      for (const line of lines) {
        if (this.y + 18 > this.bottom) this.newPage(false);
        this.drawUnitLine(line, MARGIN + 14, this.y, { size: 13, font: 'F2', color: COLORS.violet });
        this.y += 18;
      }
      this.y += 9;
      return;
    }
    if (/^references$/i.test(text)) {
      this.inReferences = true;
      if (this.y > this.bottom - 170) this.newPage(false);
    }
    const lines = wrapUnits(tokenize([{ text, font: level <= 2 ? 'F2' : 'F2' }], size), CONTENT_WIDTH - (level === 1 ? 12 : 0), size);
    for (let index = 0; index < lines.length; index += 1) {
      if (this.y + lineHeight > this.bottom) this.newPage(false);
      if (level === 1 && index === 0) this.rect(MARGIN, this.y - size + 3, 4, size + 3, { fill: COLORS.violet });
      this.drawUnitLine(lines[index], MARGIN + (level === 1 ? 12 : 0), this.y, { size, font: 'F2', color: level <= 2 ? COLORS.violet : COLORS.ink });
      this.y += lineHeight;
    }
    if (level === 2) {
      this.y += 2;
      this.line(MARGIN, this.y, PAGE_WIDTH - MARGIN, this.y, COLORS.border, 0.7);
      this.y += 5;
    } else this.y += level === 1 ? 8 : 4;
  }

  drawParagraph(value) {
    const spans = inlineSpans(value);
    const references = this.inReferences;
    const lead = this.firstParagraph;
    this.firstParagraph = false;
    this.drawRich(spans, {
      size: references ? 9.4 : 10.5,
      lineHeight: references ? 13.2 : 15.2,
      color: lead ? COLORS.muted : COLORS.ink,
      spaceBefore: lead ? 0 : 2,
      spaceAfter: references ? 6 : 9
    });
  }

  drawList(items) {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      const references = this.inReferences;
      const size = references ? 9.4 : 10.5;
      const lineHeight = references ? 13.2 : 14.8;
      const indent = MARGIN + Math.min(3, Math.floor(item.indent / 2)) * 14;
      const prefixWidth = item.ordered ? textWidth('00.', 'F2', size) + 6 : 14;
      const units = tokenize(inlineSpans(item.text), size);
      if (!units.length) continue;
      const lines = wrapUnits(units, CONTENT_WIDTH - (indent - MARGIN) - prefixWidth, size);
      const needed = Math.min(2, lines.length) * lineHeight;
      this.ensureSpace(needed + 3);
      for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
        if (this.y + lineHeight > this.bottom) this.newPage(false);
        if (lineIndex === 0) {
          if (item.ordered) this.text(`${index + 1}.`, indent, this.y, { font: 'F2', size, color: COLORS.violet });
          else this.circle(indent + 4, this.y - 3, 1.7, COLORS.violet);
        }
        this.drawUnitLine(lines[lineIndex], indent + prefixWidth, this.y, { size, font: 'F1', color: COLORS.ink });
        this.y += lineHeight;
      }
      this.y += 3;
    }
    this.y += 5;
  }

  drawQuote(value) {
    const size = 10.2;
    const lines = wrapUnits(tokenize(inlineSpans(value), size), CONTENT_WIDTH - 22, size);
    this.ensureSpace(lines.length * 14.5 + 12);
    const top = this.y - 11;
    const height = lines.length * 14.5 + 8;
    this.rect(MARGIN, top, 3, height, { fill: COLORS.lavender });
    this.rect(MARGIN + 3, top, CONTENT_WIDTH - 3, height, { fill: COLORS.lightViolet });
    this.y += 2;
    for (const line of lines) {
      if (this.y + 14.5 > this.bottom) this.newPage(false);
      this.drawUnitLine(line, MARGIN + 14, this.y, { size, font: 'F3', color: COLORS.muted });
      this.y += 14.5;
    }
    this.y += 8;
  }

  drawCode(value) {
    const size = 8.5;
    const lineHeight = 11.5;
    const maxWidth = CONTENT_WIDTH - 20;
    const lines = [];
    for (const sourceLine of String(value || '').split('\n')) {
      let remaining = normalizeText(sourceLine) || ' ';
      while (remaining) {
        let take = remaining.length;
        while (take > 1 && textWidth(remaining.slice(0, take), 'F5', size) > maxWidth) take -= 1;
        lines.push(remaining.slice(0, take));
        remaining = remaining.slice(take);
      }
    }
    for (const line of lines) {
      if (this.y + lineHeight > this.bottom) this.newPage(false);
      this.rect(MARGIN, this.y - size + 2, CONTENT_WIDTH, lineHeight, { fill: [0.965, 0.965, 0.975] });
      this.text(line, MARGIN + 8, this.y, { font: 'F5', size, color: COLORS.ink });
      this.y += lineHeight;
    }
    this.y += 7;
  }

  drawRule() {
    this.ensureSpace(10);
    this.line(MARGIN, this.y, PAGE_WIDTH - MARGIN, this.y, COLORS.border, 0.7);
    this.y += 10;
  }

  drawTable(rows) {
    if (!rows.length) return;
    const columns = Math.max(...rows.map(row => row.length));
    const columnWidth = CONTENT_WIDTH / columns;
    const size = 9.2;
    const lineHeight = 12;
    const cellPadding = 5;

    const layoutRow = row => {
      const cells = [];
      for (let column = 0; column < columns; column += 1) {
        const text = plainInline(row[column] || '');
        const units = tokenize([{ text }], size);
        const wrapped = wrapUnits(units, columnWidth - cellPadding * 2, size);
        cells.push(wrapped.map(parts => parts.map(part => part.text).join(' ')));
      }
      return cells;
    };

    const drawRow = (row, header, rowIndex = 0) => {
      const cells = layoutRow(row);
      const lineCount = Math.max(1, ...cells.map(cell => cell.length));
      const rowHeight = lineCount * lineHeight + 10;
      if (this.y + rowHeight > this.bottom) {
        this.newPage(false);
        if (!header && rows.length > 1) drawRow(rows[0], true, 0);
      }
      const top = this.y;
      for (let column = 0; column < columns; column += 1) {
        const fill = header ? COLORS.violet : (rowIndex % 2 === 0 ? COLORS.white : COLORS.lightViolet);
        const x = MARGIN + column * columnWidth;
        this.rect(x, top, columnWidth, rowHeight, { fill, stroke: COLORS.border, lineWidth: 0.5 });
        const lines = cells[column];
        if (!lines.length) lines.push('');
        lines.forEach((line, lineIndex) => {
          this.text(line, x + cellPadding, top + 12 + lineIndex * lineHeight, {
            font: header ? 'F2' : 'F1',
            size,
            color: header ? COLORS.white : COLORS.ink
          });
        });
      }
      this.y += rowHeight;
    };

    if (this.y + 44 > this.bottom) this.newPage(false);
    drawRow(rows[0], true, 0);
    for (let index = 1; index < rows.length; index += 1) drawRow(rows[index], false, index);
    this.y += 9;
  }

  render(markdown) {
    const blocks = parseMarkdown(markdown);
    if (!blocks.length) {
      this.drawParagraph('No draft content was available for export.');
      return;
    }
    for (const block of blocks) {
      if (block.type === 'heading') this.drawHeading(block.level, block.text);
      else if (block.type === 'paragraph') this.drawParagraph(block.text);
      else if (block.type === 'list') this.drawList(block.items);
      else if (block.type === 'table') this.drawTable(block.rows);
      else if (block.type === 'quote') this.drawQuote(block.text);
      else if (block.type === 'code') this.drawCode(block.text);
      else if (block.type === 'rule') this.drawRule();
    }
  }

  drawInfographicHeader(first) {
    if (first) {
      this.rect(0, 0, PAGE_WIDTH, 8, { fill: COLORS.violet });
      this.text('KnowledgePilot AI', MARGIN, 45, { font: 'F2', size: 17, color: COLORS.violet });
      this.text('LEARNING ENVIRONMENT', MARGIN, 61, { font: 'F1', size: 8.2, color: COLORS.lavender });
      const badge = 'EDUCATIONAL INFOGRAPHIC';
      const badgeWidth = textWidth(badge, 'F2', 8.2) + 22;
      this.rect(PAGE_WIDTH - MARGIN - badgeWidth, 32, badgeWidth, 18, { fill: COLORS.violet });
      this.text(badge, PAGE_WIDTH - MARGIN - badgeWidth + 11, 45, { font: 'F2', size: 8.2, color: COLORS.white });
      this.line(MARGIN, 88, PAGE_WIDTH - MARGIN, 88, COLORS.border, 0.8);
      this.text('GROUNDED INFOGRAPHIC', MARGIN, 122, { font: 'F2', size: 8.5, color: COLORS.lavender });
      const titleLines = this.wrapPlain(this.topicTitle, 'F2', 22, CONTENT_WIDTH, 3);
      let titleTop = 152;
      for (const titleLine of titleLines) {
        this.text(titleLine, MARGIN, titleTop, { font: 'F2', size: 22, color: COLORS.violet });
        titleTop += 27;
      }
      const meta = `Course: ${normalizeText(this.courseName) || 'Course materials'}  |  ${INFOGRAPHIC_LAYOUTS[this.layout] || 'Educational infographic'}  |  Exported ${formatExportDate(this.exportedAt)}`;
      const metaLine = this.wrapPlain(meta, 'F1', 9.4, CONTENT_WIDTH, 1)[0] || '';
      this.text(metaLine, MARGIN, titleTop + 6, { font: 'F1', size: 9.4, color: COLORS.muted });
      const infoTop = titleTop + 20;
      const infoText = 'Grounded in retrieved course PDF pages - verify every claim against the cited sources.';
      const infoLines = this.wrapPlain(infoText, 'F1', 8.9, CONTENT_WIDTH - 24, 2);
      const infoHeight = infoLines.length * 12 + 16;
      this.rect(MARGIN, infoTop, CONTENT_WIDTH, infoHeight, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
      infoLines.forEach((line, index) => this.text(line, MARGIN + 12, infoTop + 14 + index * 12, { font: 'F1', size: 8.9, color: COLORS.muted }));
      this.line(MARGIN, infoTop + infoHeight + 10, PAGE_WIDTH - MARGIN, infoTop + infoHeight + 10, COLORS.border, 0.6);
      this.y = infoTop + infoHeight + 30;
    } else {
      this.rect(0, 0, PAGE_WIDTH, 4, { fill: COLORS.violet });
      this.text('KnowledgePilot AI', MARGIN, 34, { font: 'F2', size: 10.5, color: COLORS.violet });
      this.text('Learning Environment', MARGIN, 46, { font: 'F1', size: 7.8, color: COLORS.lavender });
      this.text('Educational Infographic', PAGE_WIDTH - MARGIN - textWidth('Educational Infographic', 'F2', 8), 38, { font: 'F2', size: 8, color: COLORS.violet });
      this.line(MARGIN, 55, PAGE_WIDTH - MARGIN, 55, COLORS.border, 0.6);
      this.y = 82;
    }
  }

  drawIntroBox(value) {
    const lines = this.wrapPlain(value, 'F1', 10, CONTENT_WIDTH - 30, 6);
    if (!lines.length) return;
    const height = lines.length * 14.5 + 18;
    this.ensureSpace(height + 12);
    const top = this.y;
    this.rect(MARGIN, top, CONTENT_WIDTH, height, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
    this.rect(MARGIN, top, 4, height, { fill: COLORS.lavender });
    lines.forEach((line, index) => this.text(line, MARGIN + 16, top + 17 + index * 14.5, { font: 'F1', size: 10, color: COLORS.ink }));
    this.y += height + 12;
  }

  drawSectionLabel(label) {
    this.ensureSpace(26);
    this.text(String(label || '').toUpperCase(), MARGIN, this.y, { font: 'F2', size: 9, color: COLORS.lavender });
    this.y += 15;
  }

  measureConceptCard(section, width) {
    const inner = width - 28;
    const heading = this.wrapPlain(section.heading || '', 'F2', 11.5, inner, 2);
    const body = this.wrapPlain(section.body || '', 'F1', 9.4, inner, 9);
    const definition = section.definition ? this.wrapPlain(section.definition, 'F3', 8.8, inner - 12, 4) : [];
    const example = section.example ? this.wrapPlain(section.example, 'F3', 8.8, inner - 12, 4) : [];
    const height = 16 + heading.length * 15 + 4 + body.length * 12.6
      + (definition.length ? 9 + 11 + definition.length * 11.5 : 0)
      + (example.length ? 7 + 11 + example.length * 11.5 : 0) + 12;
    return { heading, body, definition, example, height };
  }

  drawConceptCard(section, index, x, top, width, layout) {
    const accent = INFOGRAPHIC_ACCENTS[index % INFOGRAPHIC_ACCENTS.length];
    this.rect(x, top, width, layout.height, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
    this.rect(x, top, 4, layout.height, { fill: accent });
    let cursor = top + 17;
    for (const line of layout.heading) {
      this.text(line, x + 16, cursor, { font: 'F2', size: 11.5, color: COLORS.violet });
      cursor += 15;
    }
    cursor += 4;
    for (const line of layout.body) {
      this.text(line, x + 16, cursor, { font: 'F1', size: 9.4, color: COLORS.ink });
      cursor += 12.6;
    }
    if (layout.definition.length) {
      cursor += 9;
      this.text('DEFINITION', x + 16, cursor, { font: 'F2', size: 7.6, color: COLORS.lavender });
      cursor += 11;
      for (const line of layout.definition) {
        this.text(line, x + 30, cursor, { font: 'F3', size: 8.8, color: COLORS.muted });
        cursor += 11.5;
      }
    }
    if (layout.example.length) {
      cursor += 7;
      this.text('EXAMPLE', x + 16, cursor, { font: 'F2', size: 7.6, color: COLORS.lavender });
      cursor += 11;
      for (const line of layout.example) {
        this.text(line, x + 30, cursor, { font: 'F3', size: 8.8, color: COLORS.muted });
        cursor += 11.5;
      }
    }
  }

  drawConceptCards(sections) {
    if (!sections || !sections.length) return;
    const gap = 12;
    const width = (CONTENT_WIDTH - gap) / 2;
    for (let index = 0; index < sections.length; index += 2) {
      const left = sections[index];
      const right = sections[index + 1];
      const leftLayout = this.measureConceptCard(left, width);
      const rightLayout = right ? this.measureConceptCard(right, width) : null;
      const height = Math.max(leftLayout.height, rightLayout?.height || 0);
      if (this.y + height > this.bottom) this.newPage(false);
      const top = this.y;
      this.drawConceptCard(left, index, MARGIN, top, width, { ...leftLayout, height });
      if (right && rightLayout) this.drawConceptCard(right, index + 1, MARGIN + width + gap, top, width, { ...rightLayout, height });
      this.y += height + 12;
    }
  }

  drawDownArrow(x, top, length, color) {
    this.line(x, top, x, top + length - 4, color, 1.2);
    const pointY = PAGE_HEIGHT - (top + length);
    const baseY = pointY + 4;
    this.op(`${color.join(' ')} rg ${(x - 3.5).toFixed(2)} ${baseY.toFixed(2)} m ${(x + 3.5).toFixed(2)} ${baseY.toFixed(2)} l ${x.toFixed(2)} ${pointY.toFixed(2)} l f`);
  }

  drawProcessSteps(steps) {
    if (!steps || !steps.length) return;
    for (let index = 0; index < steps.length; index += 1) {
      const step = steps[index];
      const inner = CONTENT_WIDTH - 58;
      const heading = this.wrapPlain(step.title || '', 'F2', 12, inner, 2);
      const detail = this.wrapPlain(step.detail || '', 'F1', 9.6, inner, 8);
      const height = 16 + heading.length * 16 + 4 + detail.length * 13 + 14;
      if (this.y + height > this.bottom) this.newPage(false);
      const top = this.y;
      const accent = INFOGRAPHIC_ACCENTS[index % INFOGRAPHIC_ACCENTS.length];
      this.rect(MARGIN, top, CONTENT_WIDTH, height, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
      this.rect(MARGIN, top, 4, height, { fill: accent });
      this.circle(MARGIN + 24, top + 23, 10, accent);
      const label = String(index + 1);
      this.text(label, MARGIN + 24 - textWidth(label, 'F2', 10) / 2, top + 27, { font: 'F2', size: 10, color: COLORS.white });
      let cursor = top + 20;
      for (const line of heading) {
        this.text(line, MARGIN + 46, cursor, { font: 'F2', size: 12, color: COLORS.violet });
        cursor += 16;
      }
      cursor += 4;
      for (const line of detail) {
        this.text(line, MARGIN + 46, cursor, { font: 'F1', size: 9.6, color: COLORS.ink });
        cursor += 13;
      }
      this.y += height;
      if (index < steps.length - 1 && this.y + 22 <= this.bottom) {
        this.drawDownArrow(MARGIN + 24, this.y + 4, 14, accent);
        this.y += 20;
      }
    }
    this.y += 8;
  }

  measureBoxList(items, width) {
    const inner = width - 30;
    const itemLines = items.map(item => this.wrapPlain(item, 'F1', 8.8, inner - 12, 4));
    const lineCount = itemLines.reduce((total, lines) => total + lines.length, 0);
    return { itemLines, height: 14 + 15 + lineCount * 11.6 + items.length * 3 + 10 };
  }

  drawBoxList(title, items, x, top, width, layout, accent) {
    this.rect(x, top, width, layout.height, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
    this.rect(x, top, 3, layout.height, { fill: accent });
    this.text(title.toUpperCase(), x + 14, top + 17, { font: 'F2', size: 9, color: accent });
    let cursor = top + 34;
    layout.itemLines.forEach(lines => {
      lines.forEach((line, index) => {
        if (index === 0) this.text('-', x + 14, cursor, { font: 'F2', size: 8.8, color: accent });
        this.text(line, x + 26, cursor, { font: 'F1', size: 8.8, color: COLORS.ink });
        cursor += 11.6;
      });
      cursor += 3;
    });
  }

  drawComparison(infographic) {
    const columns = infographic.columns || [];
    if (!columns.length) return;
    const maxPoints = Math.max(...columns.map(column => (column.points || []).length));
    const rows = [columns.map(column => column.title || '')];
    for (let index = 0; index < maxPoints; index += 1) {
      rows.push(columns.map(column => (column.points || [])[index] || ''));
    }
    this.drawTable(rows);
    const gap = 12;
    const width = (CONTENT_WIDTH - gap) / 2;
    const similarities = infographic.similarities || [];
    const differences = infographic.differences || [];
    const left = this.measureBoxList(similarities, width);
    const right = this.measureBoxList(differences, width);
    const height = Math.max(left.height, right.height);
    this.ensureSpace(height + 10);
    const top = this.y;
    this.drawBoxList('Similarities', similarities, MARGIN, top, width, { ...left, height }, INFOGRAPHIC_ACCENTS[0]);
    this.drawBoxList('Differences', differences, MARGIN + width + gap, top, width, { ...right, height }, INFOGRAPHIC_ACCENTS[1]);
    this.y += height + 14;
  }

  drawTakeaways(items) {
    if (!items || !items.length) return;
    const inner = CONTENT_WIDTH - 34;
    const itemLines = items.map(item => this.wrapPlain(item, 'F1', 9.4, inner - 12, 3));
    const lineCount = itemLines.reduce((total, lines) => total + lines.length, 0);
    const height = 18 + 14 + lineCount * 12 + items.length * 3 + 10;
    this.ensureSpace(height + 8);
    const top = this.y;
    this.rect(MARGIN, top, CONTENT_WIDTH, height, { fill: COLORS.lightViolet, stroke: COLORS.border, lineWidth: 0.5 });
    this.rect(MARGIN, top, 4, height, { fill: COLORS.violet });
    this.text('KEY TAKEAWAYS', MARGIN + 16, top + 18, { font: 'F2', size: 9, color: COLORS.violet });
    let cursor = top + 36;
    itemLines.forEach(lines => {
      lines.forEach((line, index) => {
        if (index === 0) this.circle(MARGIN + 22, cursor - 3, 1.7, COLORS.violet);
        this.text(line, MARGIN + 32, cursor, { font: 'F1', size: 9.4, color: COLORS.ink });
        cursor += 12;
      });
      cursor += 3;
    });
    this.y += height + 14;
  }

  drawInfographicSources(infographic, sources) {
    const references = (infographic.source_ids || [])
      .map(id => ({ id, source: sources[id - 1] }))
      .filter(item => item.source);
    if (!references.length) return;
    this.drawSectionLabel('Verified sources');
    for (const { id, source } of references) {
      const label = `[${id}] ${normalizeText(source.filename || 'Course PDF')} - page ${source.page ?? '?'}`;
      const labelLines = this.wrapPlain(label, 'F2', 9.2, CONTENT_WIDTH - 8, 2);
      const excerpt = this.wrapPlain(source.text || '', 'F1', 8.6, CONTENT_WIDTH - 18, 2);
      const height = labelLines.length * 12 + excerpt.length * 10.8 + 12;
      this.ensureSpace(height + 4);
      const top = this.y;
      labelLines.forEach((line, index) => this.text(line, MARGIN, top + 9 + index * 12, { font: 'F2', size: 9.2, color: COLORS.violet }));
      let cursor = top + 9 + labelLines.length * 12 + 2;
      for (const line of excerpt) {
        this.text(line, MARGIN + 10, cursor, { font: 'F1', size: 8.6, color: COLORS.muted });
        cursor += 10.8;
      }
      this.y = top + height;
      this.line(MARGIN, this.y, PAGE_WIDTH - MARGIN, this.y, COLORS.border, 0.4);
      this.y += 4;
    }
  }

  drawInfographic(infographic, sources = []) {
    if (!infographic) return;
    this.drawIntroBox(normalizeText(infographic.introduction || ''));
    const sections = Array.isArray(infographic.sections) ? infographic.sections : [];
    if (infographic.layout === 'overview') {
      this.drawSectionLabel('Concept cards');
      this.drawConceptCards(sections);
    } else if (infographic.layout === 'process') {
      this.drawSectionLabel('Process flow');
      this.drawProcessSteps(Array.isArray(infographic.steps) ? infographic.steps : []);
      if (sections.length) {
        this.drawSectionLabel('Key concepts');
        this.drawConceptCards(sections);
      }
    } else if (infographic.layout === 'comparison') {
      this.drawSectionLabel('Comparison');
      this.drawComparison(infographic);
      if (sections.length) {
        this.drawSectionLabel('Key concepts');
        this.drawConceptCards(sections);
      }
    }
    this.drawTakeaways(Array.isArray(infographic.takeaways) ? infographic.takeaways : []);
    this.drawInfographicSources(infographic, sources);
  }

  drawFooter(pageIndex, totalPages) {
    this.page = this.pages[pageIndex];
    this.line(MARGIN, PAGE_HEIGHT - 58, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 58, COLORS.border, 0.6);
    const note = this.mode === 'infographic'
      ? 'Educational infographic grounded in course PDFs - verify against the cited pages.'
      : 'AI-generated research draft - verify claims against original sources.';
    this.text(note, MARGIN, PAGE_HEIGHT - 40, { font: 'F1', size: 8.2, color: COLORS.muted });
    this.text(this.mode === 'infographic' ? 'KnowledgePilot AI · Learning Environment' : 'KnowledgePilot AI', MARGIN, PAGE_HEIGHT - 24, { font: 'F2', size: 8, color: COLORS.violet });
    const pageLabel = `Page ${pageIndex + 1} of ${totalPages}`;
    this.text(pageLabel, PAGE_WIDTH - MARGIN - textWidth(pageLabel, 'F1', 8), PAGE_HEIGHT - 24, { font: 'F1', size: 8, color: COLORS.muted });
  }

  toBytes() {
    const total = this.pages.length;
    for (let index = 0; index < total; index += 1) this.drawFooter(index, total);

    const objects = [];
    const fontEntries = [
      ['F1', 'Helvetica'],
      ['F2', 'Helvetica-Bold'],
      ['F3', 'Helvetica-Oblique'],
      ['F4', 'Helvetica-BoldOblique'],
      ['F5', 'Courier']
    ];
    objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    const kids = this.pages.map((_, index) => `${8 + index * 2} 0 R`).join(' ');
    objects[2] = `<< /Type /Pages /Kids [${kids}] /Count ${total} >>`;
    fontEntries.forEach(([name, base], index) => {
      objects[3 + index] = `<< /Type /Font /Subtype /Type1 /BaseFont /${base} /Encoding /WinAnsiEncoding >>`;
    });

    let annotationId = 8 + total * 2;
    const annotationIds = [];
    const pageObjects = [];
    this.pages.forEach((page, index) => {
      const pageId = 8 + index * 2;
      const contentId = pageId + 1;
      const ids = page.links.map(() => annotationId++);
      annotationIds.push(ids);
      const annots = ids.length ? ` /Annots [${ids.map(id => `${id} 0 R`).join(' ')}]` : '';
      pageObjects.push({
        id: pageId,
        content: page.ops.join('\n')
      });
      objects[pageId] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] /Resources << /Font << ${fontEntries.map(([name], fontIndex) => `/${name} ${3 + fontIndex} 0 R`).join(' ')} >> >> /Contents ${contentId} 0 R${annots} >>`;
      objects[contentId] = `<< /Length ${page.ops.join('\n').length} >>\nstream\n${page.ops.join('\n')}\nendstream`;
    });

    this.pages.forEach((page, pageIndex) => {
      page.links.forEach((link, linkIndex) => {
        const [x1, y1, x2, y2] = link.rect.map(value => value.toFixed(2));
        objects[annotationIds[pageIndex][linkIndex]] = `<< /Type /Annot /Subtype /Link /Rect [${x1} ${y1} ${x2} ${y2}] /Border [0 0 0] /A << /S /URI /URI (${pdfString(link.url)}) >> >>`;
      });
    });

    for (let id = 1; id < objects.length; id += 1) {
      if (!objects[id]) throw new Error(`Missing PDF object ${id}.`);
      if (!objects[id].startsWith('<<')) throw new Error(`Invalid PDF object ${id}.`);
    }

    const fileChunks = [];
    const offsets = [];
    let fileOffset = 0;
    const push = text => { fileChunks.push(text); fileOffset += text.length; };
    push(`%PDF-1.4\n%\u00e2\u00e3\u00cf\u00d3\n`);
    for (let id = 1; id < objects.length; id += 1) {
      offsets[id] = fileOffset;
      push(`${id} 0 obj\n${objects[id]}\nendobj\n`);
    }
    const xrefOffset = fileOffset;
    push(`xref\n0 ${objects.length}\n`);
    push('0000000000 65535 f \n');
    for (let id = 1; id < objects.length; id += 1) push(`${String(offsets[id]).padStart(10, '0')} 00000 n \n`);
    push(`trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`);

    const text = fileChunks.join('');
    const bytes = new Uint8Array(text.length);
    for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index) & 0xff;
    return bytes;
  }
}

export function buildResearchPdf({ answer = '', task = 'summary', topicTitle = 'Research topic', exportedAt = new Date() }) {
  const report = new PdfReport({ task, topicTitle, exportedAt });
  report.render(String(answer || ''));
  return report.toBytes();
}

export function infographicPdfFilename({ title, exportedAt = new Date() }) {
  const topic = slug(title).slice(0, 52) || 'study-topic';
  return `knowledgepilot-infographic-${topic}-${isoDate(exportedAt)}.pdf`;
}

export function buildInfographicPdf({ infographic, sources = [], courseName = '', exportedAt = new Date() }) {
  if (!infographic || typeof infographic !== 'object') throw new Error('No infographic is available to export.');
  const report = new PdfReport({
    task: 'infographic',
    topicTitle: infographic.title || 'Study infographic',
    exportedAt,
    mode: 'infographic',
    courseName,
    layout: infographic.layout
  });
  report.drawInfographic(infographic, Array.isArray(sources) ? sources : []);
  return report.toBytes();
}

export function downloadInfographicPdf({ infographic, sources = [], courseName = '', exportedAt = new Date() }) {
  if (typeof document === 'undefined' || typeof Blob === 'undefined') throw new Error('PDF download is only available in a browser.');
  const bytes = buildInfographicPdf({ infographic, sources, courseName, exportedAt });
  const filename = infographicPdfFilename({ title: infographic?.title, exportedAt });
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  const revoke = setTimeout(() => URL.revokeObjectURL(url), 60000);
  revoke?.unref?.();
  return filename;
}

export function downloadResearchPdf(options) {
  if (typeof document === 'undefined' || typeof Blob === 'undefined') throw new Error('PDF download is only available in a browser.');
  const bytes = buildResearchPdf(options);
  const filename = pdfFilename(options);
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  const revoke = setTimeout(() => URL.revokeObjectURL(url), 60000);
  revoke?.unref?.();
  return filename;
}

export function downloadResearchMarkdown({ answer = '', task = 'summary', topicTitle = 'Research topic', exportedAt = new Date() }) {
  if (typeof document === 'undefined' || typeof Blob === 'undefined') throw new Error('Markdown download is only available in a browser.');
  const filename = pdfFilename({ task, topicTitle, exportedAt }).replace(/\.pdf$/i, '.md');
  const url = URL.createObjectURL(new Blob([String(answer || '')], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  const revoke = setTimeout(() => URL.revokeObjectURL(url), 60000);
  revoke?.unref?.();
  return filename;
}

export async function copyDraftText(value) {
  if (!value) throw new Error('No draft text is available to copy.');
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(value); return; }
    catch { /* Fall back to the local selection method below. */ }
  }
  if (typeof document === 'undefined') throw new Error('Clipboard access is unavailable.');
  const area = document.createElement('textarea');
  area.value = value;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand?.('copy');
  area.remove();
  if (!copied) throw new Error('Clipboard access is unavailable.');
}

export const __pdfInternals = { parseMarkdown, inlineSpans, safeUrl, normalizeText };
