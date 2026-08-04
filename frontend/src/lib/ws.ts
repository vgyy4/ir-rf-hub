// Same Ingress-path reasoning as api.ts: resolve the socket URL relative to
// the current document location rather than assuming we're served from
// the domain root.
function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const apiBase = new URL("api/", location.href);
  return `${proto}//${apiBase.host}${apiBase.pathname}${path}`;
}

export interface RecordingCaptureMessage {
  type: "capture";
  seq: number;
  timings: number[];
}

/** Opens the scoped live-capture stream for one recording session. Returns
 * an unsubscribe function that closes the socket.
 */
export function connectRecordingSocket(
  sessionId: string,
  onCapture: (timings: number[]) => void,
): () => void {
  const socket = new WebSocket(wsUrl(`ws/recording/${sessionId}`));
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data) as RecordingCaptureMessage;
    if (message.type === "capture") {
      onCapture(message.timings);
    }
  };
  return () => socket.close();
}

export interface HubEvent {
  type: string;
  data: Record<string, unknown>;
}

/** General event fan-out: command changes, device status. Used by the home
 * screen to stay live-synced across tabs.
 */
export function connectEventSocket(onEvent: (event: HubEvent) => void): () => void {
  const socket = new WebSocket(wsUrl("ws"));
  socket.onmessage = (event) => {
    onEvent(JSON.parse(event.data) as HubEvent);
  };
  return () => socket.close();
}
