/**
 * Haptic feedback, via the best channel available.
 *
 * Two mechanisms, tried in order:
 *
 * 1. The Home Assistant Companion App's "external bus". Both the iOS and
 *    Android apps expose a JS bridge that accepts a `haptic` message and
 *    plays a real platform haptic -- on iOS that is the Taptic Engine,
 *    which the web Vibration API cannot reach at all. The bridge is
 *    injected into the *top-level* frontend window rather than our iframe,
 *    but Ingress serves this app from the same origin as Home Assistant,
 *    so window.parent / window.top are reachable and we can hand the
 *    message up. See developers.home-assistant.io/docs/frontend/external-bus.
 *
 * 2. `navigator.vibrate`, for a normal browser tab. Works on Android
 *    Chrome/Firefox; iOS Safari does not implement it, which is exactly
 *    the gap the external bus closes for Companion App users.
 *
 * Everything degrades to a silent no-op, and `prefers-reduced-motion:
 * reduce` suppresses feedback entirely. That check is read live rather
 * than cached, so toggling the OS setting takes effect without a reload.
 */

/** The haptic vocabulary the Companion App understands. */
type HaHapticType = "success" | "warning" | "failure" | "light" | "medium" | "heavy" | "selection";

interface ExternalBusWindow extends Window {
  /** Android, WebView V2 (preferred). */
  externalAppV2?: { postMessage?: (message: string) => void };
  /** Android, WebView V1 fallback. */
  externalApp?: { externalBus?: (message: string) => void };
  /** iOS / iPadOS. */
  webkit?: { messageHandlers?: { externalBus?: { postMessage?: (message: string) => void } } };
}

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** Us first, then the frames above us. Accessing a cross-origin parent
 * throws, hence the per-window try/catch -- under Ingress it is same-origin,
 * but this file should not assume it is always framed by Home Assistant. */
function bridgeCandidates(): ExternalBusWindow[] {
  const windows: ExternalBusWindow[] = [window as ExternalBusWindow];
  for (const getter of [() => window.parent, () => window.top]) {
    try {
      const candidate = getter();
      if (candidate && candidate !== window && !windows.includes(candidate as ExternalBusWindow)) {
        windows.push(candidate as ExternalBusWindow);
      }
    } catch {
      // Cross-origin frame -- nothing reachable here.
    }
  }
  return windows;
}

let messageId = 0;

/** Returns true if a bridge accepted the message. */
function sendExternalHaptic(hapticType: HaHapticType): boolean {
  const message = JSON.stringify({ id: ++messageId, type: "haptic", payload: { hapticType } });
  for (const target of bridgeCandidates()) {
    try {
      if (target.externalAppV2?.postMessage) {
        target.externalAppV2.postMessage(message);
        return true;
      }
      if (target.externalApp?.externalBus) {
        target.externalApp.externalBus(message);
        return true;
      }
      const ios = target.webkit?.messageHandlers?.externalBus;
      if (ios?.postMessage) {
        ios.postMessage(message);
        return true;
      }
    } catch {
      // Bridge present but unhappy, or the frame turned out to be
      // cross-origin after all -- fall through to the next candidate.
    }
  }
  return false;
}

function vibrate(pattern: number | number[]): void {
  if (typeof navigator === "undefined" || !("vibrate" in navigator)) return;
  try {
    navigator.vibrate(pattern);
  } catch {
    // Some webviews throw instead of no-op'ing when vibration is blocked
    // by policy. Feedback is never load-bearing, so swallow it.
  }
}

function feedback(hapticType: HaHapticType, pattern: number | number[]): void {
  if (reducedMotion()) return;
  if (sendExternalHaptic(hapticType)) return;
  vibrate(pattern);
}

export const haptics = {
  /** A command was tapped, a wizard step advanced, a choice was made. */
  tap: () => feedback("light", 10),
  /** A signal landed while recording -- distinct from `tap` so you can feel
   * captures without looking at the screen while pointing a remote. */
  capture: () => feedback("medium", 25),
  /** Fired, paired, copied, saved. */
  success: () => feedback("success", [15, 40, 15]),
  /** Request failed. Unmistakably not a success. */
  error: () => feedback("failure", [40, 30, 40]),
};
