<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import { editWizard } from "../../stores/edit.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithTransmitter } from "../../api";
  import { haptics } from "../../haptics";
  import RouterIcon from "@lucide/svelte/icons/router";
  import PencilRulerIcon from "@lucide/svelte/icons/pencil-ruler";
  import ChevronRightIcon from "@lucide/svelte/icons/chevron-right";

  const wizard = editWizard;

  let candidateDevices = $derived(
    wizard.command ? devicesWithTransmitter(devicesStore.items, wizard.command.type) : [],
  );

  const isOpen = $derived(wizard.step === "choose-action" || wizard.step === "choose-default-device");

  async function save() {
    await wizard.saveDefaultDevice();
    if (wizard.error) haptics.error();
    else haptics.success();
  }
</script>

<Modal open={isOpen} onClose={() => wizard.close()}>
  {#if wizard.step === "choose-action"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">{wizard.command?.name}</h2>
    <p class="text-muted-foreground mb-4 text-sm">What would you like to do with this command?</p>
    <div class="flex flex-col gap-2">
      <button
        type="button"
        class="press border-border bg-card hover:bg-muted focus-visible:border-ring focus-visible:ring-ring/50 flex items-center gap-3 rounded-lg border p-4 text-left transition-colors outline-none focus-visible:ring-3"
        onclick={() => {
          haptics.tap();
          wizard.goToChooseDefaultDevice();
        }}
      >
        <RouterIcon class="text-primary size-5 shrink-0" />
        <span class="flex-1">
          <strong class="block">Choose / change default ESP</strong>
          <span class="text-muted-foreground text-sm">
            Set which device sends this command when tapped from the home screen.
          </span>
        </span>
        <ChevronRightIcon class="text-muted-foreground size-4 shrink-0" />
      </button>
      <button
        type="button"
        class="press border-border bg-card hover:bg-muted focus-visible:border-ring focus-visible:ring-ring/50 flex items-center gap-3 rounded-lg border p-4 text-left transition-colors outline-none focus-visible:ring-3"
        onclick={() => {
          haptics.tap();
          wizard.goToRawEditor();
        }}
      >
        <PencilRulerIcon class="text-primary size-5 shrink-0" />
        <span class="flex-1">
          <strong class="block">Alter command</strong>
          <span class="text-muted-foreground text-sm">Directly edit the raw signal payload.</span>
        </span>
        <ChevronRightIcon class="text-muted-foreground size-4 shrink-0" />
      </button>
    </div>
    <div class="mt-5 flex justify-end">
      <Button variant="secondary" onclick={() => wizard.close()}>Cancel</Button>
    </div>
  {:else if wizard.step === "choose-default-device"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Default ESP</h2>
    <p class="text-muted-foreground mb-4 text-sm">
      Choose the device that should send "{wizard.command?.name}" by default.
    </p>
    <DevicePicker
      devices={candidateDevices}
      selectedId={wizard.selectedDefaultDeviceId}
      onSelect={(id) => (wizard.selectedDefaultDeviceId = id)}
    />
    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="mt-5 flex justify-end gap-2">
      <Button variant="secondary" onclick={() => wizard.close()}>Cancel</Button>
      <Button disabled={!wizard.selectedDefaultDeviceId || wizard.busy} onclick={save}>Save</Button>
    </div>
  {/if}
</Modal>
