import {
  createCommand,
  searchRemoteDatabase,
  testFireRaw,
  type CommandDetail,
  type RemoteSearchResult,
  type SignalType,
} from "../api";

export type SearchStep = "closed" | "choose-type" | "search" | "name" | "done";

const SEARCH_DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 2;

class SearchWizard {
  step = $state<SearchStep>("closed");
  type = $state<SignalType | null>(null);
  query = $state("");
  results = $state<RemoteSearchResult[]>([]);
  searching = $state(false);
  searchError = $state<string | null>(null);
  selected = $state<RemoteSearchResult | null>(null);
  name = $state("");
  repeatCount = $state(1);
  error = $state<string | null>(null);
  busy = $state(false);
  savedName = $state<string | null>(null);

  // Test-fire, same rationale as edit.svelte.ts's: separate state so it
  // can't clobber (or be clobbered by) the save flow's own busy/error.
  showTestFirePicker = $state(false);
  testFireBusy = $state(false);
  testFireError = $state<string | null>(null);
  testFireSuccess = $state(false);

  private debounceTimer: ReturnType<typeof setTimeout> | undefined;
  private testFireSuccessTimer: ReturnType<typeof setTimeout> | undefined;
  // Bumped on every new search; a response is only applied if it's still
  // the most recent one requested -- without this, typing quickly can let
  // an earlier (slower) response land after a later (faster) one and show
  // stale results for what's currently in the box.
  private searchSeq = 0;

  open() {
    this.step = "choose-type";
    this.type = null;
    this.query = "";
    this.results = [];
    this.searching = false;
    this.searchError = null;
    this.selected = null;
    this.name = "";
    this.repeatCount = 1;
    this.error = null;
    this.busy = false;
    this.savedName = null;
    this.showTestFirePicker = false;
    this.testFireError = null;
    this.testFireSuccess = false;
  }

  chooseType(type: SignalType) {
    this.type = type;
    this.query = "";
    this.results = [];
    this.searchError = null;
    this.step = "search";
  }

  /** Debounced, cancellation-safe live search-as-you-type. */
  onQueryChange() {
    clearTimeout(this.debounceTimer);
    this.searchError = null;
    if (this.query.trim().length < MIN_QUERY_LENGTH) {
      this.results = [];
      this.searching = false;
      this.searchSeq++; // invalidate any in-flight search
      return;
    }
    this.searching = true;
    this.debounceTimer = setTimeout(() => void this.runSearch(), SEARCH_DEBOUNCE_MS);
  }

  private async runSearch() {
    if (!this.type) return;
    const seq = ++this.searchSeq;
    try {
      const results = await searchRemoteDatabase(this.query.trim(), this.type);
      if (seq !== this.searchSeq) return;
      this.results = results;
    } catch (e) {
      if (seq !== this.searchSeq) return;
      this.searchError = String(e);
      this.results = [];
    } finally {
      if (seq === this.searchSeq) this.searching = false;
    }
  }

  pickResult(result: RemoteSearchResult) {
    this.selected = result;
    this.name = `${result.brand} ${result.model} ${result.button}`;
    this.repeatCount = result.repeat_count;
    this.error = null;
    this.step = "name";
  }

  back() {
    this.error = null;
    if (this.step === "name") {
      this.selected = null;
      this.showTestFirePicker = false;
      this.step = "search";
    } else if (this.step === "search") {
      this.type = null;
      this.step = "choose-type";
    }
  }

  get canGoBack() {
    return this.step === "search" || this.step === "name";
  }

  get canFinish() {
    return this.selected !== null && this.name.trim().length > 0;
  }

  async testFire(deviceId: string) {
    if (!this.selected) return;
    this.testFireBusy = true;
    this.testFireError = null;
    try {
      await testFireRaw({
        type: this.type ?? "ir",
        device_id: deviceId,
        raw_timings: this.selected.raw_timings,
        carrier_frequency_hz: this.selected.carrier_frequency_hz,
        repeat_count: this.repeatCount,
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

  async finish(): Promise<CommandDetail | null> {
    if (!this.canFinish || !this.selected || !this.type) return null;
    this.busy = true;
    this.error = null;
    try {
      const command = await createCommand({
        name: this.name.trim(),
        type: this.type,
        raw_timings: this.selected.raw_timings,
        carrier_frequency_hz: this.selected.carrier_frequency_hz,
        repeat_count: this.repeatCount,
      });
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

  /** Back to searching (same type) rather than the whole wizard, so
   * finding several commands off the same search doesn't mean re-picking
   * IR/RF every time -- mirrors recording.svelte.ts's recordAnother(). */
  searchAnother() {
    this.selected = null;
    this.name = "";
    this.savedName = null;
    this.error = null;
    this.showTestFirePicker = false;
    this.step = "search";
  }

  close() {
    this.step = "closed";
  }
}

export const searchWizard = new SearchWizard();
