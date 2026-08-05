import {
  clearRecording,
  createCommand,
  discardRecording,
  receiverFrequencyHz,
  startRecording,
  stopRecording,
  type CommandDetail,
  type SignalType,
} from "../api";
import { devicesStore } from "./devices.svelte";
import { connectRecordingSocket } from "../ws";

export type RecordStep = "closed" | "choose-type" | "choose-device" | "recording" | "name";

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
      this.finalTimings = result.timings;
      this.repeatCount = Math.max(1, result.capture_count);
      this.unsubscribeWs?.();
      this.unsubscribeWs = null;
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  proceedToName() {
    if (this.finalTimings) this.step = "name";
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
