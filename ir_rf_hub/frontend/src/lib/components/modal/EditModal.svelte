<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import { editWizard } from "../../stores/edit.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithTransmitter } from "../../api";
  import RouterIcon from "@lucide/svelte/icons/router";
  import PencilRulerIcon from "@lucide/svelte/icons/pencil-ruler";
  import ChevronRightIcon from "@lucide/svelte/icons/chevron-right";

  const wizard = editWizard;

  let candidateDevices = $derived(
    wizard.command ? devicesWithTransmitter(devicesStore.items, wizard.command.type) : [],
  );

  const isOpen = $derived(wizard.step === "choose-action" || wizard.step === "choose-default-device");
</script>

<Modal open={isOpen} onClose={() => wizard.close()}>
  {#if wizard.step === "choose-action"}
    <h2 class="h4 mb-1">{wizard.command?.name}</h2>
    <p class="text-surface-600-400 mb-4 text-sm">What would you like to do with this command?</p>
    <div class="flex flex-col gap-2">
      <button
        type="button"
        class="card preset-filled-surface-100-900 hover:preset-tonal-primary flex items-center gap-3 p-4 text-left transition-colors"
        onclick={() => wizard.goToChooseDefaultDevice()}
      >
        <RouterIcon class="text-primary-500 size-5 shrink-0" />
        <span class="flex-1">
          <strong class="block">Choose / change default ESP</strong>
          <span class="text-surface-600-400 text-sm">Set which device sends this command when tapped from the home screen.</span>
        </span>
        <ChevronRightIcon class="text-surface-500 size-4 shrink-0" />
      </button>
      <button
        type="button"
        class="card preset-filled-surface-100-900 hover:preset-tonal-primary flex items-center gap-3 p-4 text-left transition-colors"
        onclick={() => wizard.goToRawEditor()}
      >
        <PencilRulerIcon class="text-primary-500 size-5 shrink-0" />
        <span class="flex-1">
          <strong class="block">Alter command</strong>
          <span class="text-surface-600-400 text-sm">Directly edit the raw signal payload.</span>
        </span>
        <ChevronRightIcon class="text-surface-500 size-4 shrink-0" />
      </button>
    </div>
    <div class="mt-5 flex justify-end">
      <button type="button" class="btn preset-tonal" onclick={() => wizard.close()}>Cancel</button>
    </div>
  {:else if wizard.step === "choose-default-device"}
    <h2 class="h4 mb-1">Default ESP</h2>
    <p class="text-surface-600-400 mb-4 text-sm">Choose the device that should send "{wizard.command?.name}" by default.</p>
    <DevicePicker
      devices={candidateDevices}
      selectedId={wizard.selectedDefaultDeviceId}
      onSelect={(id) => (wizard.selectedDefaultDeviceId = id)}
    />
    {#if wizard.error}<p class="text-error-500 mt-2 text-sm">{wizard.error}</p>{/if}
    <div class="mt-5 flex justify-end gap-2">
      <button type="button" class="btn preset-tonal" onclick={() => wizard.close()}>Cancel</button>
      <button
        type="button"
        class="btn preset-filled-primary-500"
        disabled={!wizard.selectedDefaultDeviceId || wizard.busy}
        onclick={() => wizard.saveDefaultDevice()}
      >
        Save
      </button>
    </div>
  {/if}
</Modal>
