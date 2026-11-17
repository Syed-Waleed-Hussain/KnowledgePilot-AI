import { trapDialogFocus } from './dialogFocus.js';
import { useEffect, useRef, useState } from 'react';
import { Menu, X } from 'lucide-react';

export function NavigationToggle({ onClick, label = 'Open navigation' }) {
  return <button type="button" className="navigation-toggle" aria-label={label} aria-haspopup="dialog" onClick={onClick}><Menu size={20}/></button>;
}

// A native modal supplies focus containment, background inertness and Escape.
// Render the same navigation once: an aside on desktop, a dialog on mobile.
export default function ResponsiveSidebar({ children, className, open, onClose, label }) {
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches);
  const dialog = useRef(null);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 768px)');
    const change = () => { setMobile(media.matches); onClose(); };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    if (!mobile || !open) return;
    const previous = document.activeElement;
    const node = dialog.current;
    node.showModal();
    return () => { node.close(); if (previous?.isConnected) previous.focus({preventScroll:true}); };
  }, [mobile, open]);
  if (!mobile) return <aside className={className} aria-label={label}>{children}</aside>;
  return <dialog onKeyDown={trapDialogFocus} ref={dialog} className={`navigation-drawer ${className}`} aria-label={label}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) { const r=event.currentTarget.getBoundingClientRect(); if(event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) onClose(); } }}>
    <div className="drawer-heading"><strong>{label}</strong><button type="button" aria-label="Close navigation" onClick={onClose} autoFocus><X size={20}/></button></div>
    {children}
  </dialog>;
}
