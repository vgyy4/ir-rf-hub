// Same Ingress-path reasoning as api.ts: resolve the socket URL relative to
// the current document location rather than assuming we're served from
// the domain root.
function wsUrl(path: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const apiBase = new URL("api/", location.href);
  return `${proto}//${apiBase.host}${apiBase.pathname}${path}`;
}

const RECONNECT_INITIAL_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;

/** Opens `path` as a WebSocket and keeps it open: on any drop (backend
 * restart, Ingress token rotation, a brief network blip -- all things that
 * happen to a long-lived tab), reconnects with exponential backoff
 * (1s, 2s, 4s, ... capped at 30s, reset to 1s on the next successful
 * connect) rather than leaving the caller silently stale until a page
 * reload. Mirrors the companion integration's own WS reconnect loop
 * (api.py's async_listen_events) for the same reason: it's a plain retry
 * loop around the socket, not a queue -- `onmessage` just keeps firing
 * across reconnects, and a REST resync (already how these callers each
 * establish their starting state) is the correctness backstop for
 * whatever was missed while disconnected.
 *
 * Returns an unsubscribe function that stops reconnecting and closes the
 * current socket for good.
 */
function connectWithReconnect(
  path: string,
  onMessage: (event: MessageEvent) => void,
  onReconnect?: () => void,
): () => void {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let delay = RECONNECT_INITIAL_DELAY_MS;
  let stopped = false;
  let everConnected = false;

  function open() {
    if (stopped) return;
    socket = new WebSocket(wsUrl(path));
    socket.onmessage = onMessage;
    socket.onopen = () => {
      delay = RECONNECT_INITIAL_DELAY_MS;
      // Only a *re*connect (not the first connect, which the caller's own
      // initial REST fetch already covers) needs to trigger a resync --
      // this is the backstop for whatever events were missed while the
      // socket was down.
      if (everConnected) onReconnect?.();
      everConnected = true;
    };
    socket.onclose = () => {
      if (stopped) return;
      reconnectTimer = setTimeout(open, delay);
      delay = Math.min(delay * 2, RECONNECT_MAX_DELAY_MS);
    };
  }
  open();

  return () => {
    stopped = true;
    clearTimeout(reconnectTimer);
    socket?.close();
  };
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
  return connectWithReconnect(`ws/recording/${sessionId}`, (event) => {
    const message = JSON.parse(event.data) as RecordingCaptureMessage;
    if (message.type === "capture") {
      onCapture(message.timings);
    }
  });
}

export interface HubEvent {
  type: string;
  data: Record<string, unknown>;
}

/** General event fan-out: command changes, device status. Used by the home
 * screen to stay live-synced across tabs. `onReconnect` fires after every
 * *re*connect (not the first connect) so the caller can do a full REST
 * resync to catch anything missed while the socket was down.
 */
export function connectEventSocket(
  onEvent: (event: HubEvent) => void,
  onReconnect?: () => void,
): () => void {
  return connectWithReconnect(
    "ws",
    (event) => {
      onEvent(JSON.parse(event.data) as HubEvent);
    },
    onReconnect,
  );
}
