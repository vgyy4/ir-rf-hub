<script lang="ts">
  import Modal from "./Modal.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import DevicePicker from "../DevicePicker.svelte";
  import { editWizard } from "../../stores/edit.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { devicesWithTransmitter } from "../../api";
  import { haptics } from "../../haptics";
  import CheckIcon from "@lucide/svelte/icons/check";
  import RadioTowerIcon from "@lucide/svelte/icons/radio-tower";

  const wizard = editWizard;

  // See RecordModal: actions can't attach to components, so focus goes
  // through Input's bindable `ref` instead.
  let newNameInput = $state<HTMLInputElement | null>(null);
  $effect(() => {
    newNameInput?.focus();
  });

  function cancel() {
    wizard.close();
  }

  async function save() {
    await wizard.saveEdited();
    if (wizard.error) haptics.error();
    else haptics.success();
  }

  async function saveAsNew() {
    await wizard.saveAsNewCommand();
    if (wizard.error) haptics.error();
    else haptics.success();
  }

  const testFireDevices = $derived(
    wizard.command ? devicesWithTransmitter(devicesStore.items, wizard.command.type) : [],
  );

  function toggleTestFirePicker() {
    haptics.tap();
    wizard.showTestFirePicker = !wizard.showTestFirePicker;
    wizard.testFireError = null;
  }

  async function handleTestFireDevicePicked(deviceId: string) {
    await wizard.testFire(deviceId);
    if (wizard.testFireError) haptics.error();
    else haptics.success();
  }
</script>

<Modal open={wizard.step === "raw-editor"} onClose={cancel} fullscreen>
  <div class="flex h-full flex-col">
    <header class="mb-4">
      <h2 class="mb-1 text-lg font-semibold tracking-tight">
        Alter command &mdash; {wizard.command?.name}
      </h2>
      <p class="text-muted-foreground text-sm">
        Comma-separated raw timings in microseconds. Positive = mark (on), negative = space (off) --
        the same format the device recorded.
      </p>
    </header>

    <!-- Signal payloads stay on the always-dark console treatment used by
         TerminalView, in every palette -- this is raw instrument data. -->
    <textarea
      class="focus-visible:ring-ring/50 min-h-0 flex-1 resize-none rounded-lg bg-neutral-950 p-4 font-mono text-sm text-green-400 outline-none focus-visible:ring-3"
      bind:value={wizard.rawTimingsText}
      spellcheck="false"
    ></textarea>

    <label class="mt-3 block">
      <span class="text-muted-foreground text-sm">Repeat signal (optional)</span>
      <textarea
        class="focus-visible:ring-ring/50 mt-1 h-20 w-full resize-none rounded-lg bg-neutral-950 p-3 font-mono text-sm text-green-400 outline-none focus-visible:ring-3"
        bind:value={wizard.repeatTimingsText}
        placeholder="Leave empty for a plain single-shape command"
        spellcheck="false"
      ></textarea>
      <span class="text-muted-foreground mt-1 block text-xs">
        If set, the signal above fires once and this fires for any repeats beyond the first --
        instead of resending the same signal every time. Matches how some remotes (e.g. NEC-style)
        send an initial signal once, then switch to a distinct, shorter repeat signal while held.
      </span>
    </label>

    <label class="mt-3 block">
      <span class="text-muted-foreground text-sm">Repeat count</span>
      <Input type="number" class="mt-1 w-32" min="1" bind:value={wizard.repeatCount} />
    </label>

    <div class="mt-3">
      <Button variant="outline" size="sm" onclick={toggleTestFirePicker}>
        {#if wizard.testFireSuccess}
          <CheckIcon class="text-success" />
          Sent
        {:else}
          <RadioTowerIcon />
          Test fire
        {/if}
      </Button>
      <span class="text-muted-foreground ml-2 text-xs">
        Sends what's in the boxes above right now, without saving it first.
      </span>

      {#if wizard.showTestFirePicker}
        <div class="bg-card border-border mt-2 space-y-2 rounded-lg border p-3">
          {#if wizard.testFireError}
            <Alert.Root variant="destructive">
              <Alert.Description>{wizard.testFireError}</Alert.Description>
            </Alert.Root>
          {/if}
          <DevicePicker
            devices={testFireDevices}
            selectedId={null}
            onSelect={handleTestFireDevicePicked}
          />
        </div>
      {/if}
    </div>

    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}

    {#if wizard.showSaveAsNewPrompt}
      <div class="mt-4 flex items-center gap-2">
        <Input
          type="text"
          class="flex-1"
          placeholder="New command name"
          bind:value={wizard.newCommandName}
          bind:ref={newNameInput}
        />
        <Button variant="secondary" onclick={() => (wizard.showSaveAsNewPrompt = false)}>
          Back
        </Button>
        <Button disabled={!wizard.newCommandName.trim() || wizard.busy} onclick={saveAsNew}>
          Confirm
        </Button>
      </div>
    {:else}
      <div class="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onclick={cancel}>Cancel</Button>
        <Button
          variant="secondary"
          disabled={wizard.busy}
          onclick={() => (wizard.showSaveAsNewPrompt = true)}
        >
          Save to a new command
        </Button>
        <Button disabled={wizard.busy} onclick={save}>Save</Button>
      </div>
    {/if}
  </div>
</Modal>
