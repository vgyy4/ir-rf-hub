import {
  clearRecording,
  createCommand,
  discardRecording,
  receiverFrequencyHz,
  startRecording,
  stopRecording,
  type CommandDetail,
  type DetectedProtocolInfo,
  type ShapeCandidate,
  type SignalType,
} from "../api";
import { devicesStore } from "./devices.svelte";
import { connectRecordingSocket } from "../ws";

export type RecordStep = "closed" | "choose-type" | "choose-device" | "recording" | "choose-shapes" | "name";

// Only two roles exist today (leader + repeat, matching the only
// multi-shape protocol the backend knows how to detect -- see
// signal_shapes.py) -- so the picker caps selection at 2 rather than
// supporting an arbitrary-length sequence.
const MAX_SELECTABLE_SHAPES = 2;

class RecordingWizard {
  step = $state<RecordStep>("closed");
  type = $state<SignalType | null>(null);
  deviceId = $state<string | null>(null);
  sessionId = $state<string | null>(null);
  /** Each entry is one full raw-signal capture (mark/space pairs), as they
   * arrive live -- see recording_ws.py: ir_rf_proxy delivers a whole press
   * atomically, not byte by byte, so the terminal renders capture-sized
   * chunks rather than a true per-sample stream.
   */
  captures = $state<number[][]>([]);
  finalTimings = $state<number[] | null>(null);
  /** Set only for a two-shape command (leader = finalTimings, this =
   * the repeat shape) -- either auto-detected (detectedProtocol set) or
   * chosen by the user in the "choose-shapes" step.
   */
  repeatTimings = $state<number[] | null>(null);
  /** Informational: which known protocol matched, if repeatTimings came
   * from detection rather than a user choice. Shown in the "name" step.
   */
  detectedProtocol = $state<DetectedProtocolInfo | null>(null);
  /** Populated only when stopRecording() couldn't resolve to a single
   * shape or a recognized protocol -- the "choose-shapes" step shows
   * these and lets the user pick up to 2.
   */
  shapeCandidates = $state<ShapeCandidate[] | null>(null);
  selectedShapeIndices = $state<Set<number>>(new Set());
  carrierFrequencyHz = $state(0);
  /** Many remotes send the same code several times per button press --
   * the ESP delivers each repeat as its own capture (see captures above),
   * so how many arrived during one recording is exactly how many times
   * to repeat on transmit. Auto-filled in stopRecording(), user-editable
   * in the "name" step: a receiver that expects N repeats to debounce
   * noise won't act on a single one, regardless of how correct that one
   * capture is.
   */
  repeatCount = $state(1);
  name = $state("");
  error = $state<string | null>(null);
  busy = $state(false);

  private unsubscribeWs: (() => void) | null = null;

  get canProceedFromDevice() {
    return this.deviceId !== null;
  }

  get canProceedFromRecording() {
    return this.finalTimings !== null || this.shapeCandidates !== null;
  }

  get canProceedFromShapes() {
    return this.selectedShapeIndices.size > 0;
  }

  get canFinish() {
    return this.name.trim().length > 0;
  }

  open() {
    this.step = "choose-type";
    this.type = null;
    this.deviceId = null;
    this.sessionId = null;
    this.captures = [];
    this.finalTimings = null;
    this.repeatTimings = null;
    this.detectedProtocol = null;
    this.shapeCandidates = null;
    this.selectedShapeIndices = new Set();
    this.carrierFrequencyHz = 0;
    this.repeatCount = 1;
    this.name = "";
    this.error = null;
    this.busy = false;
  }

  chooseType(type: SignalType) {
    this.type = type;
    this.step = "choose-device";
    this.deviceId = null;
  }

  chooseDevice(deviceId: string) {
    this.deviceId = deviceId;
  }

  async startRecording() {
    if (!this.type || !this.deviceId) return;
    this.busy = true;
    this.error = null;
    try {
      const resp = await startRecording(this.type, this.deviceId);
      this.sessionId = resp.session_id;
      this.captures = [];
      this.finalTimings = null;
      this.repeatTimings = null;
      this.detectedProtocol = null;
      this.shapeCandidates = null;
      this.selectedShapeIndices = new Set();
      this.repeatCount = 1;
      this.carrierFrequencyHz = receiverFrequencyHz(devicesStore.items, this.deviceId, this.type);
      this.step = "recording";
      this.unsubscribeWs = connectRecordingSocket(resp.session_id, (timings) => {
        this.captures = [...this.captures, timings];
      });
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  async clearAndRetry() {
    if (!this.sessionId) return;
    this.busy = true;
    this.error = null;
    try {
      await clearRecording(this.sessionId);
      this.captures = [];
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  async stopRecording() {
    if (!this.sessionId) return;
    this.busy = true;
    this.error = null;
    try {
      const result = await stopRecording(this.sessionId);
      this.repeatCount = Math.max(1, result.capture_count);
      this.unsubscribeWs?.();
      this.unsubscribeWs = null;

      if (result.timings) {
        // Every capture was the same shape -- the common case, ready to
        // save as-is.
        this.finalTimings = result.timings;
      } else if (result.detected_protocol) {
        // A recognized multi-shape protocol (e.g. NEC leader + repeat) --
        // both parts save together, no user choice needed.
        this.finalTimings = result.detected_protocol.leader_timings;
        this.repeatTimings = result.detected_protocol.repeat_timings;
        this.detectedProtocol = result.detected_protocol;
      } else if (result.shape_candidates) {
        // Multiple distinct shapes, no recognized protocol -- the
        // "choose-shapes" step (see proceedFromRecording) lets the user
        // pick. Default selection: whichever shape(s) tie for the most
        // edges, matching the same "most complete capture" heuristic
        // used when there's only one shape.
        this.shapeCandidates = result.shape_candidates;
        const maxEdges = Math.max(...result.shape_candidates.map((c) => c.edge_count));
        this.selectedShapeIndices = new Set(
          result.shape_candidates.flatMap((c, i) => (c.edge_count === maxEdges ? [i] : [])),
        );
      }
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  proceedFromRecording() {
    if (this.shapeCandidates) {
      this.step = "choose-shapes";
    } else if (this.finalTimings) {
      this.step = "name";
    }
  }

  /** Toggles one shape candidate, capping selection at
   * MAX_SELECTABLE_SHAPES by dropping the oldest selection to make room --
   * simpler than a hard block for a two-role (leader/repeat) picker.
   */
  toggleShapeSelection(index: number) {
    const next = new Set(this.selectedShapeIndices);
    if (next.has(index)) {
      next.delete(index);
    } else {
      if (next.size >= MAX_SELECTABLE_SHAPES) {
        const oldest = next.values().next().value;
        if (oldest !== undefined) next.delete(oldest);
      }
      next.add(index);
    }
    this.selectedShapeIndices = next;
  }

  /** The selected shape with the most edges becomes the leader
   * (finalTimings); a second selection, if any, becomes the repeat
   * shape -- deterministic regardless of click order.
   */
  confirmShapeSelection() {
    if (!this.shapeCandidates || this.selectedShapeIndices.size === 0) return;
    const chosen = [...this.selectedShapeIndices]
      .map((i) => this.shapeCandidates![i])
      .sort((a, b) => b.edge_count - a.edge_count);
    this.finalTimings = chosen[0].timings;
    this.repeatTimings = chosen.length > 1 ? chosen[1].timings : null;
    this.step = "name";
  }

  async finish(): Promise<CommandDetail | null> {
    if (!this.canFinish || !this.finalTimings || !this.type) return null;
    this.busy = true;
    this.error = null;
    try {
      const command = await createCommand({
        name: this.name.trim(),
        type: this.type,
        raw_timings: this.finalTimings,
        carrier_frequency_hz: this.carrierFrequencyHz,
        repeat_count: this.repeatCount,
        recorded_from_device_id: this.deviceId,
        repeat_timings: this.repeatTimings,
        repeat_protocol: this.detectedProtocol?.name ?? null,
      });
      this.step = "closed";
      return command;
    } catch (e) {
      this.error = String(e);
      return null;
    } finally {
      this.busy = false;
    }
  }

  /** Closes the modal from any step, discarding an in-progress recording
   * session on the backend if one is still open so the device's half-duplex
   * lock is released promptly rather than waiting for the App to notice
   * the tab went away.
   */
  async close() {
    if (this.sessionId && this.step === "recording") {
      try {
        await discardRecording(this.sessionId);
      } catch {
        // best-effort; the session will still be cleaned up if the
        // WebSocket disconnect is what the backend actually relies on
      }
    }
    this.unsubscribeWs?.();
    this.unsubscribeWs = null;
    this.step = "closed";
  }
}

export const recordingWizard = new RecordingWizard();
