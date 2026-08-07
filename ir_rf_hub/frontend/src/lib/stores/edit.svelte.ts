import { createCommand, getCommand, testFireRaw, updateCommand, type CommandDetail, type CommandSummary } from "../api";
import { parseOptionalTimingsText, parseTimingsText } from "../timings";

export type EditStep = "closed" | "choose-action" | "choose-default-device" | "raw-editor";

class EditWizard {
  step = $state<EditStep>("closed");
  command = $state<CommandDetail | null>(null);
  selectedDefaultDeviceId = $state<string | null>(null);
  rawTimingsText = $state("");
  /** Optional -- a two-shape command's repeat signal (see
   * signal_shapes.py). Empty text means "no repeat signal" / cleared.
   */
  repeatTimingsText = $state("");
  repeatCount = $state(1);
  showSaveAsNewPrompt = $state(false);
  newCommandName = $state("");
  busy = $state(false);
  error = $state<string | null>(null);

  // Test-fire: separate state from the save flow above so a failed test
  // shot never blocks/clobbers an in-progress save (and vice versa).
  showTestFirePicker = $state(false);
  testFireBusy = $state(false);
  testFireError = $state<string | null>(null);
  testFireSuccess = $state(false);
  private testFireSuccessTimer: ReturnType<typeof setTimeout> | undefined;

  async open(summary: CommandSummary) {
    this.step = "choose-action";
    this.busy = true;
    this.error = null;
    this.showSaveAsNewPrompt = false;
    try {
      this.command = await getCommand(summary.id);
      this.selectedDefaultDeviceId = this.command.default_device_id;
      this.rawTimingsText = this.command.raw_timings.join(", ");
      this.repeatTimingsText = this.command.repeat_timings?.join(", ") ?? "";
      this.repeatCount = this.command.repeat_count;
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  goToChooseDefaultDevice() {
    this.step = "choose-default-device";
  }

  goToRawEditor() {
    this.step = "raw-editor";
  }

  async saveDefaultDevice() {
    if (!this.command || !this.selectedDefaultDeviceId) return;
    this.busy = true;
    this.error = null;
    try {
      await updateCommand(this.command.id, { default_device_id: this.selectedDefaultDeviceId });
      this.close();
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  /** Parses the editor's comma-separated textarea into raw timings, or
   * returns null if the text isn't a valid list of integers.
   */
  parseRawTimings(): number[] | null {
    return parseTimingsText(this.rawTimingsText);
  }

  /** Same format, but empty text is valid here -- it means "no repeat
   * signal", not an error. Returns undefined (distinct from null) if the
   * text is non-empty but not a valid list of integers.
   */
  parseRepeatTimings(): number[] | null | undefined {
    return parseOptionalTimingsText(this.repeatTimingsText);
  }

  async saveEdited() {
    const timings = this.parseRawTimings();
    const repeatTimings = this.parseRepeatTimings();
    if (!this.command || !timings || repeatTimings === undefined) {
      this.error = "Raw timings must be a comma-separated list of integers";
      return;
    }
    this.busy = true;
    this.error = null;
    try {
      await updateCommand(this.command.id, {
        raw_timings: timings,
        repeat_count: this.repeatCount,
        repeat_timings: repeatTimings,
        // A manually-edited repeat signal no longer reflects what (if
        // anything) was auto-detected -- only keep the label if the
        // repeat signal itself is unchanged from what was loaded.
        repeat_protocol:
          repeatTimings !== null && this.repeatTimingsText === (this.command.repeat_timings?.join(", ") ?? "")
            ? this.command.repeat_protocol
            : null,
      });
      this.close();
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  async saveAsNewCommand() {
    const timings = this.parseRawTimings();
    const repeatTimings = this.parseRepeatTimings();
    if (!this.command || !timings || repeatTimings === undefined) {
      this.error = "Raw timings must be a comma-separated list of integers";
      return;
    }
    if (!this.newCommandName.trim()) {
      this.error = "Enter a name for the new command";
      return;
    }
    this.busy = true;
    this.error = null;
    try {
      // Original command is deliberately left untouched -- only the new
      // one carries the edited payload.
      await createCommand({
        name: this.newCommandName.trim(),
        type: this.command.type,
        raw_timings: timings,
        carrier_frequency_hz: this.command.carrier_frequency_hz,
        repeat_count: this.repeatCount,
        repeat_timings: repeatTimings,
        repeat_protocol:
          repeatTimings !== null && this.repeatTimingsText === (this.command.repeat_timings?.join(", ") ?? "")
            ? this.command.repeat_protocol
            : null,
      });
      this.close();
    } catch (e) {
      this.error = String(e);
    } finally {
      this.busy = false;
    }
  }

  /** Fires the editor's current (possibly unsaved) raw timings against a
   * chosen device -- lets you verify a hand-edited signal actually does
   * something before committing to Save. Uses whatever's in the textareas
   * right now, not what's persisted, so editing then testing then editing
   * again always tests the latest text.
   */
  async testFire(deviceId: string) {
    const timings = this.parseRawTimings();
    const repeatTimings = this.parseRepeatTimings();
    if (!this.command || !timings || repeatTimings === undefined) {
      this.testFireError = "Raw timings must be a comma-separated list of integers";
      return;
    }
    this.testFireBusy = true;
    this.testFireError = null;
    try {
      await testFireRaw({
        type: this.command.type,
        device_id: deviceId,
        raw_timings: timings,
        carrier_frequency_hz: this.command.carrier_frequency_hz,
        repeat_count: this.repeatCount,
        repeat_timings: repeatTimings,
      });
      this.testFireSuccess = true;
      clearTimeout(this.testFireSuccessTimer);
      this.testFireSuccessTimer = setTimeout(() => (this.testFireSuccess = false), 2200);
    } catch (e) {
      this.testFireError = String(e);
    } finally {
      this.testFireBusy = false;
    }
  }

  close() {
    this.step = "closed";
    this.command = null;
    this.showSaveAsNewPrompt = false;
    this.newCommandName = "";
    this.showTestFirePicker = false;
    this.testFireError = null;
    this.testFireSuccess = false;
    clearTimeout(this.testFireSuccessTimer);
  }
}

export const editWizard = new EditWizard();
