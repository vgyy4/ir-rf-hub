import { createCommand, getCommand, updateCommand, type CommandDetail, type CommandSummary } from "../api";

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
    return this._parseTimingsText(this.rawTimingsText, /* allowEmpty */ false);
  }

  /** Same format, but empty text is valid here -- it means "no repeat
   * signal", not an error. Returns undefined (distinct from null) if the
   * text is non-empty but not a valid list of integers.
   */
  parseRepeatTimings(): number[] | null | undefined {
    if (this.repeatTimingsText.trim().length === 0) return null;
    const parsed = this._parseTimingsText(this.repeatTimingsText, /* allowEmpty */ false);
    return parsed ?? undefined;
  }

  private _parseTimingsText(text: string, allowEmpty: boolean): number[] | null {
    const parts = text
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (parts.length === 0) return allowEmpty ? [] : null;
    const nums = parts.map(Number);
    if (nums.some((n) => !Number.isInteger(n))) return null;
    return nums;
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

  close() {
    this.step = "closed";
    this.command = null;
    this.showSaveAsNewPrompt = false;
    this.newCommandName = "";
  }
}

export const editWizard = new EditWizard();
