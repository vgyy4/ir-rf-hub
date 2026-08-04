/** Focuses an element on mount. Svelte's own `autofocus` attribute lint
 * (a11y_autofocus) flags the raw HTML attribute; using an action instead
 * is the idiomatic way to keep the same behavior without the warning.
 */
export function autofocus(node: HTMLElement) {
  node.focus();
}
