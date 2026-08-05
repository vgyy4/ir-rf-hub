// Ingress typically serves the App over plain http (not https/localhost),
// which is not a "secure context" -- `navigator.clipboard` is undefined
// there, so calling it directly throws and the button silently does
// nothing. Falls back to the legacy execCommand technique via the DOM
// Selection API in that case.
export async function copyElementText(el: HTMLElement, text: string): Promise<boolean> {
  if (await copyWithClipboardApi(text)) return true;
  return copyWithSelectionExecCommand(el);
}

async function copyWithClipboardApi(text: string): Promise<boolean> {
  if (!navigator.clipboard) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

// Selects the visible element's text and copies via the DOM Selection,
// rather than creating+focusing a detached <textarea>. A modal's Dialog
// runs a focus trap that lives inside its own portal -- focusing an
// element appended to document.body (outside that subtree) gets
// immediately yanked back inside the trap, so execCommand("copy") ends up
// copying nothing (or stale content) while still reporting success.
// Selecting existing in-modal content sidesteps that.
function copyWithSelectionExecCommand(el: HTMLElement): boolean {
  const selection = window.getSelection();
  if (!selection) return false;
  const range = document.createRange();
  range.selectNodeContents(el);
  selection.removeAllRanges();
  selection.addRange(range);
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    selection.removeAllRanges();
  }
}
