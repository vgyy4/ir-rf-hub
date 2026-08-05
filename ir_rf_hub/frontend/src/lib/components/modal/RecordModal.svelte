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
      {wizard.finalTimings ? "Signal captured." : "Point the remote at the receiver and press a button."}
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
        disabled={wizard.busy || !!wizard.finalTimings}
      >
        Stop recording
      </button>
      <button
        type="button"
        class="btn preset-filled-primary-500"
        disabled={!wizard.finalTimings || wizard.busy}
        onclick={() => wizard.proceedToName()}
      >
        Next
      </button>
    </div>
  {:else if wizard.step === "name"}
    <h2 class="h4 mb-1">Name this function</h2>
    <p class="text-surface-600-400 mb-3 text-sm">e.g. "TV Power" or "Living Room Fan Speed 2"</p>
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
