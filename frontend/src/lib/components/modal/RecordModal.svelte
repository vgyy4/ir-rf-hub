<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import TerminalView from "../TerminalView.svelte";
  import { recordingWizard } from "../../stores/recording.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithReceiver } from "../../api";
  import { autofocus } from "../../actions";

  const wizard = recordingWizard;

  let candidateDevices = $derived(wizard.type ? devicesWithReceiver(devicesStore.items, wizard.type) : []);

  async function handleClose() {
    await wizard.close();
  }
</script>

<Modal open={wizard.step !== "closed"} onClose={handleClose}>
  {#if wizard.step === "choose-type"}
    <h2>New Recording</h2>
    <p class="hint">What kind of signal are you recording?</p>
    <div class="type-choice">
      <button type="button" class="type-button" onclick={() => wizard.chooseType("ir")}>
        <span class="icon">📡</span>
        Infrared (IR)
      </button>
      <button type="button" class="type-button" onclick={() => wizard.chooseType("rf")}>
        <span class="icon">📻</span>
        Radio Frequency (RF)
      </button>
    </div>

  {:else if wizard.step === "choose-device"}
    <h2>Choose a receiver</h2>
    <p class="hint">Which ESPHome device should listen for the signal?</p>
    <DevicePicker devices={candidateDevices} selectedId={wizard.deviceId} onSelect={(id) => wizard.chooseDevice(id)} />
    {#if wizard.error}<p class="error">{wizard.error}</p>{/if}
    <div class="actions">
      <button type="button" class="secondary" onclick={handleClose}>Cancel</button>
      <button type="button" disabled={!wizard.canProceedFromDevice || wizard.busy} onclick={() => wizard.startRecording()}>
        Next
      </button>
    </div>

  {:else if wizard.step === "recording"}
    <h2>Recording&hellip;</h2>
    <p class="hint">
      {wizard.finalTimings ? "Signal captured." : "Point the remote at the receiver and press a button."}
    </p>
    <TerminalView captures={wizard.captures} />
    {#if wizard.error}<p class="error">{wizard.error}</p>{/if}
    <div class="actions">
      <button type="button" class="secondary" onclick={() => wizard.clearAndRetry()} disabled={wizard.busy}>
        Clear &amp; retry
      </button>
      <button type="button" class="secondary" onclick={() => wizard.stopRecording()} disabled={wizard.busy || !!wizard.finalTimings}>
        Stop recording
      </button>
      <button type="button" disabled={!wizard.finalTimings || wizard.busy} onclick={() => wizard.proceedToName()}>
        Next
      </button>
    </div>

  {:else if wizard.step === "name"}
    <h2>Name this function</h2>
    <p class="hint">e.g. "TV Power" or "Living Room Fan Speed 2"</p>
    <input
      type="text"
      class="name-input"
      bind:value={wizard.name}
      placeholder="Function name"
      use:autofocus
    />
    {#if wizard.error}<p class="error">{wizard.error}</p>{/if}
    <div class="actions">
      <button type="button" class="secondary" onclick={handleClose}>Cancel</button>
      <button type="button" disabled={!wizard.canFinish || wizard.busy} onclick={() => wizard.finish()}>
        Finish
      </button>
    </div>
  {/if}
</Modal>

<style>
  h2 {
    margin: 0 0 0.25rem;
  }

  .hint {
    color: #9aa4b2;
    margin: 0 0 1.25rem;
    font-size: 0.9rem;
  }

  .type-choice {
    display: flex;
    gap: 0.75rem;
  }

  .type-button {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 1.5rem 1rem;
    border-radius: 12px;
    border: 1px solid #333944;
    background: #22262e;
    color: inherit;
    cursor: pointer;
    font-size: 1rem;
  }

  .type-button:hover {
    border-color: #58a6ff;
  }

  .icon {
    font-size: 1.75rem;
  }

  .name-input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.65rem 0.85rem;
    border-radius: 8px;
    border: 1px solid #333944;
    background: #14161a;
    color: inherit;
    font-size: 1rem;
    margin-bottom: 1rem;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1.25rem;
  }

  button {
    padding: 0.55rem 1.1rem;
    border-radius: 8px;
    border: none;
    background: #2f81f7;
    color: white;
    font-size: 0.9rem;
    cursor: pointer;
  }

  button:disabled {
    background: #384150;
    color: #6b7280;
    cursor: not-allowed;
  }

  button.secondary {
    background: transparent;
    border: 1px solid #333944;
    color: inherit;
  }

  .error {
    color: #ff6b6b;
    font-size: 0.85rem;
  }

  @media (prefers-color-scheme: light) {
    .type-button,
    .name-input {
      background: #f3f4f6;
      border-color: #d1d5db;
    }
    .hint {
      color: #555;
    }
  }
</style>
