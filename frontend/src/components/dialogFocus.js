// Keep keyboard focus in the dialog, including the browser-chrome Tab boundary.
export function trapDialogFocus(event) {
  if (event.key !== 'Tab') return;
  const node = event.currentTarget;
  const items = [...node.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter(item => item.tabIndex >= 0 && item.getClientRects().length > 0);
  if (!items.length) { event.preventDefault(); node.focus(); return; }
  const first = items[0], last = items[items.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === node)) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
}
