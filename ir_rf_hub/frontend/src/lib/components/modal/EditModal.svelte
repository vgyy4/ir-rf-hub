<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import { editWizard } from "../../stores/edit.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithTransmitter } from "../../api";

  const wizard = editWizard;

  let candidateDevices = $derived(
    wizard.command ? devicesWithTransmitter(devicesStore.items, wizard.command.type) : [],
  );

  const isOpen = $derived(wizard.step === "choose-action" || wizard.step === "choose-default-device");
</script>

<Modal open={isOpen} onClose={() => wizard.close()}>
  {#if wizard.step === "choose-action"}
    <h2>{wizard.command?.name}</h2>
    <p class="hint">What would you like to do with this command?</p>
    <div class="actions-stack">
      <button type="button" class="option" onclick={() => wizard.goToChooseDefaultDevice()}>
        <strong>Choose / change default ESP</strong>
        <span>Set which device sends this command when tapped from the home screen.</span>
      </button>
      <button type="button" class="option" onclick={() => wizard.goToRawEditor()}>
        <strong>Alter command</strong>
        <span>Directly edit the raw signal payload.</span>
      </button>
    </div>
    <div class="actions">
      <button type="button" class="secondary" onclick={() => wizard.close()}>Cancel</button>
    </div>

  {:else if wizard.step === "choose-default-device"}
    <h2>Default ESP</h2>
    <p class="hint">Choose the device that should send "{wizard.command?.name}" by default.</p>
    <DevicePicker
      devices={candidateDevices}
      selectedId={wizard.selectedDefaultDeviceId}
      onSelect={(id) => (wizard.selectedDefaultDeviceId = id)}
    />
    {#if wizard.error}<p class="error">{wizard.error}</p>{/if}
    <div class="actions">
      <button type="button" class="secondary" onclick={() => wizard.close()}>Cancel</button>
      <button
        type="button"
        disabled={!wizard.selectedDefaultDeviceId || wizard.busy}
        onclick={() => wizard.saveDefaultDevice()}
      >
        Save
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

  .actions-stack {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .option {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    text-align: left;
    padding: 1rem;
    border-radius: 10px;
    border: 1px solid #333944;
    background: #22262e;
    color: inherit;
    cursor: pointer;
  }

  .option:hover {
    border-color: #58a6ff;
  }

  .option span {
    font-size: 0.82rem;
    color: #9aa4b2;
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
    .option {
      background: #f3f4f6;
      border-color: #d1d5db;
    }
  }
</style>
