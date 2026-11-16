// Render the actual component without a browser or an extra testing library.
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: MarkdownAnswer } = await server.ssrLoadModule('/src/components/MarkdownAnswer.jsx');
  const text = '**Vision encoder**\n\n- First\n- Second\n\n1. Step\n\n```js\nconst a = 1;\n```\n\n| Source | Page |\n|---|---|\n| PDF | 1 |\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))';
  const html = renderToStaticMarkup(React.createElement(MarkdownAnswer, { text }));
  for (const tag of ['strong', 'ul', 'ol', 'pre', 'code', 'table']) assert.ok(html.includes(`<${tag}`), tag);
  assert.ok(!html.includes('<script'));
  assert.ok(!html.includes('href="javascript:'));
  console.log('PASS: actual Markdown component renders bold, lists, code and tables; strips HTML and unsafe URLs.');
} finally {
  await server.close();
}
