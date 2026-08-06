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
import { parseOptionalTimingsText, parseTimingsText, TIMINGS_FORMAT_ERROR } from "../timings";

export type RecordStep =
  | "closed"
  | "choose-type"
  | "choose-device"
  | "raw"
  | "recording"
  | "choose-shapes"
  | "name"
  | "done";

/** The de-facto standard IR carrier. Only used for hand-written raw
 * commands, where there's no receiving entity to read the real carrier
 * from (see receiverFrequencyHz) -- most IR receivers ignore a
 * transmission at the wrong carrier entirely, so a sane default matters.
 * RF is unmodulated, hence 0. */
const DEFAULT_IR_CARRIER_HZ = 38000;

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

  /** Hand-written raw entry (the "write raw" path off the device step).
   * Same comma-separated format as the edit wizard's raw editor. */
  rawTimingsText = $state("");
  repeatTimingsText = $state("");
  /** True when finalTimings came from `raw` rather than a live recording.
   * Decides where Back goes from the name step, and whether "Record
   * another" has a device to reuse. */
  enteredRawManually = $state(false);
  /** Name of the command just saved, shown on the `done` step. */
  savedName = $state<string | null>(null);

  private unsubscribeWs: (() => void) | null = null;

  /** True once anything has been captured. The recording step's only
   * forward action is Next, which stops the session itself (see
   * stopAndProceed) -- so this gates on having *something* to keep, not on
   * the session already having been stopped. */
  get canProceedFromRecording() {
    return this.captures.length > 0 || this.finalTimings !== null || this.shapeCandidates !== null;
  }

  /** True once the backend has resolved the session into a keepable shape. */
  private get isStopped() {
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
    this.rawTimingsText = "";
    this.repeatTimingsText = "";
    this.enteredRawManually = false;
    this.savedName = null;
  }

  chooseType(type: SignalType) {
    this.type = type;
    this.step = "choose-device";
    this.deviceId = null;
  }

  /** Picking a receiver is the whole content of that step, so it starts
   * the recording immediately rather than making the user confirm a
   * choice they just made. Back is how you undo it. */
  async chooseDevice(deviceId: string) {
    this.deviceId = deviceId;
    await this.startRecording();
  }

  /** The alternative to recording: type the timings in by hand, for a
   * signal you already have from a datasheet, another tool, or a device
   * that isn't reachable right now. */
  goToRawEntry() {
    this.step = "raw";
    this.enteredRawManually = true;
    this.rawTimingsText = "";
    this.repeatTimingsText = "";
    this.repeatCount = 1;
    this.carrierFrequencyHz = this.type === "ir" ? DEFAULT_IR_CARRIER_HZ : 0;
    this.error = null;
  }

  /** Validates the hand-written timings and moves on to naming. Mirrors
   * what stopRecording() produces, so the name step and finish() can't
   * tell the two paths apart. */
  confirmRawEntry() {
    const timings = parseTimingsText(this.rawTimingsText);
    const repeat = parseOptionalTimingsText(this.repeatTimingsText);
    if (!timings) {
      this.error = TIMINGS_FORMAT_ERROR;
      return;
    }
    if (repeat === undefined) {
      this.error = `Repeat signal: ${TIMINGS_FORMAT_ERROR.toLowerCase()}`;
      return;
    }
    this.finalTimings = timings;
    this.repeatTimings = repeat;
    this.detectedProtocol = null;
    this.shapeCandidates = null;
    this.error = null;
    this.step = "name";
  }

  /** One step back, wherever that means for the current step. Discards a
   * live recording session on the way out of `recording` so the device's
   * half-duplex lock is released rather than held until timeout. */
  async back() {
    this.error = null;
    switch (this.step) {
      case "choose-device":
        this.step = "choose-type";
        this.type = null;
        break;
      case "raw":
        this.enteredRawManually = false;
        this.step = "choose-device";
        break;
      case "recording":
        await this.discardSession();
        this.captures = [];
        this.finalTimings = null;
        this.shapeCandidates = null;
        this.selectedShapeIndices = new Set();
        // deviceId is deliberately kept: the picker shows it still
        // selected, and tapping it again restarts recording.
        this.step = "choose-device";
        break;
      case "choose-shapes":
        this.step = "recording";
        break;
      case "name":
        this.step = this.enteredRawManually
          ? "raw"
          : this.shapeCandidates
            ? "choose-shapes"
            : "recording";
        break;
    }
  }

  get canGoBack() {
    return (
      this.step === "choose-device" ||
      this.step === "raw" ||
      this.step === "recording" ||
      this.step === "choose-shapes" ||
      this.step === "name"
    );
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
      this.enteredRawManually = false;
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

  /** The recording step's single forward action: stop the session (if it is
   * still running) and move on in one press. Separating "stop" from "next"
   * made the user confirm something they had already decided by pressing a
   * button labelled Next. */
  async stopAndProceed() {
    if (!this.isStopped) {
      await this.stopRecording();
      if (this.error) return;
    }
    this.proceedFromRecording();
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
      // Lands on `done` rather than closing outright, so capturing a
      // second command off the same remote doesn't mean walking the whole
      // wizard again -- see recordAnother().
      this.savedName = command.name;
      this.step = "done";
      return command;
    } catch (e) {
      this.error = String(e);
      return null;
    } finally {
      this.busy = false;
    }
  }

  /** Straight back into a live recording on the same signal type and the
   * same receiver. Falls back to the device step when there's no device to
   * reuse, which is the case after a hand-written raw command. */
  async recordAnother() {
    this.name = "";
    this.savedName = null;
    this.error = null;
    if (!this.type) {
      this.step = "choose-type";
      return;
    }
    if (!this.deviceId || this.enteredRawManually) {
      this.enteredRawManually = false;
      this.step = "choose-device";
      return;
    }
    await this.startRecording();
  }

  /** Best-effort release of a live recording session. The backend also
   * cleans up on WebSocket disconnect, so a failure here is not fatal. */
  private async discardSession() {
    if (!this.sessionId) return;
    try {
      await discardRecording(this.sessionId);
    } catch {
      // see above
    }
    this.unsubscribeWs?.();
    this.unsubscribeWs = null;
    this.sessionId = null;
  }

  /** Closes the modal from any step, discarding an in-progress recording
   * session on the backend if one is still open so the device's half-duplex
   * lock is released promptly rather than waiting for the App to notice
   * the tab went away.
   */
  async close() {
    if (this.step === "recording") {
      await this.discardSession();
    }
    this.unsubscribeWs?.();
    this.unsubscribeWs = null;
    this.step = "closed";
  }
}

export const recordingWizard = new RecordingWizard();
