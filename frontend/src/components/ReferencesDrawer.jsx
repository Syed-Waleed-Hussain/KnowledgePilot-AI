import { useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'motion/react';

export default function ReferencesDrawer({ sources, onClose }) {
  const dialog = useRef(null);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    const previousFocus = document.activeElement;
    dialog.current.showModal();
    return () => { dialog.current?.close(); previousFocus?.focus(); };
  }, []);

  // Native dialog handles focus trapping; Escape and the backdrop also close it.
  return <dialog ref={dialog} className="references-dialog" aria-labelledby="references-title"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { const bounds = dialog.current.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right) onClose(); }}>
    <motion.aside initial={{ x: reducedMotion ? 0 : 25, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: .2 }}>
      <header className="source-head"><h2 id="references-title">Sources &amp; References</h2>
        <button autoFocus className="close-source" aria-label="Close references" onClick={onClose}>×</button></header>
      {sources.map((source, index) => <article className="reference-passage" key={`${source.filename}-${source.page}-${index}`}>
        <h3>[{index + 1}] {source.filename}</h3><span>PDF page {source.page}</span><p>{source.text}</p>
      </article>)}
    </motion.aside>
  </dialog>;
}
