import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function MarkdownAnswer({ text }) {
  return <div className="markdown-answer"><Markdown skipHtml remarkPlugins={[remarkGfm]}
    disallowedElements={['img']}
    urlTransform={url => /^(https?:\/\/|mailto:|#)/i.test(url) ? url : ''}
    components={{ a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}
  >{text}</Markdown></div>;
}
