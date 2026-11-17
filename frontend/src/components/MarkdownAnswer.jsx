import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Stable renderers preserve table scroll position when the composer rerenders.
const components = {
  table: ({ children }) => <div className="markdown-table-scroll" role="region"
    aria-label="Answer table, scroll horizontally if needed" tabIndex={0}>
    <table>{children}</table>
  </div>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
};

const headings = {
  2: {h1: ({children}) => <h2>{children}</h2>, h2: ({children}) => <h3>{children}</h3>, h3: ({children}) => <h4>{children}</h4>, h4: ({children}) => <h5>{children}</h5>, h5: ({children}) => <h6>{children}</h6>},
  3: {h1: ({children}) => <h3>{children}</h3>, h2: ({children}) => <h4>{children}</h4>, h3: ({children}) => <h5>{children}</h5>, h4: ({children}) => <h6>{children}</h6>, h5: ({children}) => <h6>{children}</h6>},
};
const readingComponents = {2: {...components,...headings[2]}, 3: {...components,...headings[3]}};

export default function MarkdownAnswer({ text, headingLevel = 2 }) {
  return <div className="markdown-answer"><Markdown skipHtml remarkPlugins={[remarkGfm]}
    disallowedElements={['img']}
    urlTransform={url => /^(https?:\/\/|mailto:|#)/i.test(url) ? url : ''}
    components={readingComponents[headingLevel] || readingComponents[2]}
  >{text}</Markdown></div>;
}
