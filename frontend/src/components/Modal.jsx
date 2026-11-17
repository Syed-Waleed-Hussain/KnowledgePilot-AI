import { trapDialogFocus } from './dialogFocus.js';
import { useEffect, useRef } from 'react';
export default function Modal({ children, onClose, labelledBy }) {
  const ref=useRef(null);
  useEffect(()=>{ const previous=document.activeElement, node=ref.current; node.showModal(); return ()=>{node.close();previous?.focus({preventScroll:true});}; },[]);
  return <dialog onKeyDown={trapDialogFocus} ref={ref} className="course-dialog" aria-labelledby={labelledBy} onCancel={event=>{event.preventDefault();onClose();}} onClick={event=>{if(event.target===event.currentTarget){const r=event.currentTarget.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)onClose();}}}>{children}</dialog>;
}
