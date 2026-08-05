<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import TerminalView from "../TerminalView.svelte";
  import { recordingWizard } from "../../stores/recording.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithReceiver } from "../../api";
  import { autofocus } from "../../actions";
  import RadioIcon from "@lucide/svelte/icons/radio";
  import AntennaIcon from "@lucide/svelte/icons/antenna";

  const wizard = recordingWizard;

  let candidateDevices = $derived(wizard.type ? devicesWithReceiver(devicesStore.items, wizard.type) : []);

  async function handleClose() {
    await wizard.close();
  }
</script>

<Modal open={wizard.step !== "closed"} onClose={handleClose}>
  {#if wizard.step === "choose-type"}
    <h2 class="h4 mb-1">New Recording</h2>
    <p class="text-surface-600-400 mb-5 text-sm">What kind of signal are you recording?</p>
    <div class="flex gap-3">
      <button
        type="button"
        class="card preset-filled-surface-100-900 hover:preset-tonal-primary flex flex-1 flex-col items-center gap-2 p-6 transition-colors"
        onclick={() => wizard.chooseType("ir")}
      >
        <RadioIcon class="text-primary-500 size-7" />
        Infrared (IR)
      </button>
      <button
        type="button"
        class="card preset-filled-surface-100-900 hover:preset-tonal-tertiary flex flex-1 flex-col items-center gap-2 p-6 transition-colors"
        onclick={() => wizard.chooseType("rf")}
      >
        <AntennaIcon class="text-tertiary-500 size-7" />
        Radio Frequency (RF)
      </button>
    </div>
  {:else if wizard.step === "choose-device"}
    <h2 class="h4 mb-1">Choose a receiver</h2>
    <p class="text-surface-600-400 mb-5 text-sm">Which ESPHome device should listen for the signal?</p>
    <DevicePicker devices={candidateDevices} selectedId={wizard.deviceId} onSelect={(id) => wizard.chooseDevice(id)} />
    {#if wizard.error}<p class="text-error-500 mt-2 text-sm">{wizard.error}</p>{/if}
    <div class="mt-5 flex justify-end gap-2">
      <button type="button" class="btn preset-tonal" onclick={handleClose}>Cancel</button>
      <button
        type="button"
        class="btn preset-filled-primary-500"
        disabled={!wizard.canProceedFromDevice || wizard.busy}
        onclick={() => wizard.startRecording()}
      >
        Next
      </button>
    </div>
  {:else if wizard.step === "recording"}
    <h2 class="h4 mb-1">Recording&hellip;</h2>
    <p class="text-surface-600-400 mb-5 text-sm">
      {wizard.canProceedFromRecording ? "Signal captured." : "Point the remote at the receiver and press a button."}
    </p>
    <TerminalView captures={wizard.captures} />
    {#if wizard.error}<p class="text-error-500 mt-2 text-sm">{wizard.error}</p>{/if}
    <div class="mt-5 flex flex-wrap justify-end gap-2">
      <button type="button" class="btn preset-tonal" onclick={() => wizard.clearAndRetry()} disabled={wizard.busy}>
        Clear &amp; retry
      </button>
      <button
        type="button"
        class="btn preset-tonal"
        onclick={() => wizard.stopRecording()}
        disabled={wizard.busy || wizard.canProceedFromRecording}
      >
        Stop recording
      </button>
      <button
        type="button"
        class="btn preset-filled-primary-500"
        disabled={!wizard.canProceedFromRecording || wizard.busy}
        onclick={() => wizard.proceedFromRecording()}
      >
        Next
      </button>
    </div>
  {:else if wizard.step === "choose-shapes"}
    <h2 class="h4 mb-1">Multiple signals captured</h2>
    <p class="text-surface-600-400 mb-5 text-sm">
      These didn't look like the same signal repeated, and didn't match a known pattern either --
      choose which one to keep (or two, if your remote sends an initial signal plus a distinct
      repeat signal while held).
    </p>
    <ul class="flex max-h-80 flex-col gap-2 overflow-y-auto">
      {#each wizard.shapeCandidates ?? [] as candidate, i (i)}
        <li>
          <button
            type="button"
            class={[
              "card w-full p-3 text-left transition-colors",
              wizard.selectedShapeIndices.has(i)
                ? "preset-tonal-primary border-primary-500 border"
                : "preset-filled-surface-100-900 hover:preset-tonal-surface border border-transparent",
            ].join(" ")}
            onclick={() => wizard.toggleShapeSelection(i)}
          >
            <div class="flex items-center justify-between gap-3">
              <span class="font-mono text-xs">
                {candidate.timings
                  .slice(0, 6)
                  .map((t) => (t >= 0 ? `+${t}` : `${t}`))
                  .join(" ")}{candidate.timings.length > 6 ? " …" : ""}
              </span>
              <span class="text-surface-500 shrink-0 text-xs">
                {candidate.edge_count} edges &middot; seen {candidate.occurrences}&times;
              </span>
            </div>
          </button>
        </li>
      {/each}
    </ul>
    <p class="text-surface-500 mt-3 text-xs">
      Pick up to two: the first is used as-is, a second becomes a distinct repeat signal (sent for
      any repeats beyond the first, instead of resending the same one).
    </p>
    {#if wizard.error}<p class="text-error-500 mt-2 text-sm">{wizard.error}</p>{/if}
    <div class="mt-5 flex justify-end gap-2">
      <button type="button" class="btn preset-tonal" onclick={() => (wizard.step = "recording")}>Back</button>
      <button
        type="button"
        class="btn preset-filled-primary-500"
        disabled={!wizard.canProceedFromShapes}
        onclick={() => wizard.confirmShapeSelection()}
      >
        Next
      </button>
    </div>
  {:else if wizard.step === "name"}
    <h2 class="h4 mb-1">Name this function</h2>
    <p class="text-surface-600-400 mb-3 text-sm">e.g. "TV Power" or "Living Room Fan Speed 2"</p>
    {#if wizard.detectedProtocol}
      <p class="text-surface-600-400 preset-tonal-primary mb-4 rounded-lg p-2 text-xs">
        Detected a leader signal plus a distinct repeat signal ({wizard.detectedProtocol.name}) -- both
        will be saved.
      </p>
    {:else if wizard.repeatTimings}
      <p class="text-surface-600-400 preset-tonal-primary mb-4 rounded-lg p-2 text-xs">
        Saving two signals: the one you picked first, plus a distinct repeat signal.
      </p>
    {/if}
    <input type="text" class="input mb-4" bind:value={wizard.name} placeholder="Function name" use:autofocus />
    <label class="mb-4 block">
      <span class="text-surface-600-400 text-sm">Repeat count</span>
      <input type="number" class="input mt-1" min="1" bind:value={wizard.repeatCount} />
      <span class="text-surface-500 mt-1 block text-xs">
        How many times to send the signal when fired. Pre-filled with how many times your remote
        repeated it during recording -- some receivers need to see the same code several times in
        a row to act on it.
      </span>
    </label>
    {#if wizard.error}<p class="text-error-500 mb-2 text-sm">{wizard.error}</p>{/if}
    <div class="flex justify-end gap-2">
      <button type="button" class="btn preset-tonal" onclick={handleClose}>Cancel</button>
      <button type="button" class="btn preset-filled-primary-500" disabled={!wizard.canFinish || wizard.busy} onclick={() => wizard.finish()}>
        Finish
      </button>
    </div>
  {/if}
</Modal>
