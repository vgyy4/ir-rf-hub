/**
 * Haptic feedback for phones and tablets.
 *
 * Wraps the Vibration API, which is supported on Android (Chrome, Firefox,
 * and the HA companion app's webview) and NOT on iOS Safari -- there is no
 * web API that reaches the Taptic Engine, so on iPhone/iPad every call here
 * is a deliberate no-op rather than a broken feature. Desktop browsers
 * generally expose `vibrate` but have no vibration hardware, which is also a
 * silent no-op.
 *
 * Vibration is motion, so `prefers-reduced-motion: reduce` suppresses it.
 * That check is read live rather than cached at import, so toggling the OS
 * setting takes effect without a reload.
 */

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function buzz(pattern: number | number[]): void {
  if (typeof navigator === "undefined" || !("vibrate" in navigator)) return;
  if (reducedMotion()) return;
  try {
    navigator.vibrate(pattern);
  } catch {
    // Some webviews throw instead of no-op'ing when vibration is blocked by
    // policy. Feedback is never load-bearing, so swallow it.
  }
}

export const haptics = {
  /** A command was tapped, a wizard step advanced, a choice was made. */
  tap: () => buzz(10),
  /** A signal landed while recording -- distinct from `tap` so you can feel
   * captures without looking at the screen while pointing a remote. */
  capture: () => buzz(25),
  /** Fired, paired, copied, saved. */
  success: () => buzz([15, 40, 15]),
  /** Request failed. Longer and rougher so it is unmistakably not a success. */
  error: () => buzz([40, 30, 40]),
};
