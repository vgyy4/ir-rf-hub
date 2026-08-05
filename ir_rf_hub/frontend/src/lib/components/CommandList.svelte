<script lang="ts">
  import CommandRow from "./CommandRow.svelte";
  import Modal from "./modal/Modal.svelte";
  import DevicePicker from "./DevicePicker.svelte";
  import { commandsStore } from "../stores/commands.svelte";
  import {
    candidateDevicesForCommand,
    deleteCommand,
    fireCommand,
    type CommandSummary,
    type EspDeviceSummary,
  } from "../api";
  import InboxIcon from "@lucide/svelte/icons/inbox";

  interface Props {
    onEdit: (command: CommandSummary) => void;
  }

  let { onEdit }: Props = $props();

  let firePickerCommand = $state<CommandSummary | null>(null);
  let firePickerDevices = $state<EspDeviceSummary[]>([]);
  let fireError = $state<string | null>(null);

  let deleteConfirmCommand = $state<CommandSummary | null>(null);
  let deleteBusy = $state(false);
  let deleteError = $state<string | null>(null);

  function handleDeleteRequest(command: CommandSummary) {
    deleteError = null;
    deleteConfirmCommand = command;
  }

  async function handleDeleteConfirmed() {
    if (!deleteConfirmCommand) return;
    deleteBusy = true;
    deleteError = null;
    try {
      await deleteCommand(deleteConfirmCommand.id);
      await commandsStore.refresh();
      deleteConfirmCommand = null;
    } catch (e) {
      deleteError = String(e);
    } finally {
      deleteBusy = false;
    }
  }

  async function handleFire(command: CommandSummary) {
    fireError = null;
    if (command.default_device_id) {
      try {
        await fireCommand(command.id);
      } catch (e) {
        fireError = String(e);
      }
      return;
    }
    // No default set -- ask which ESP, filtered to transmitters of the
    // matching IR/RF type (server-side filter, see candidate-devices).
    firePickerCommand = command;
    firePickerDevices = await candidateDevicesForCommand(command.id);
  }

  async function handleDevicePicked(deviceId: string) {
    if (!firePickerCommand) return;
    try {
      await fireCommand(firePickerCommand.id, deviceId);
    } catch (e) {
      fireError = String(e);
    } finally {
      firePickerCommand = null;
    }
  }
</script>

{#if commandsStore.loading && commandsStore.items.length === 0}
  <p class="text-surface-500 text-sm">Loading&hellip;</p>
{:else if commandsStore.items.length === 0}
  <div class="border-surface-300-700 flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center">
    <InboxIcon class="text-surface-500 size-8" />
    <p class="text-surface-500 text-sm">
      No recordings yet. Tap "New Recording" to capture your first IR or RF command.
    </p>
  </div>
{:else}
  <ul class="flex flex-col gap-2">
    {#each commandsStore.items as command (command.id)}
      <CommandRow {command} onFire={handleFire} {onEdit} onDelete={handleDeleteRequest} />
    {/each}
  </ul>
{/if}

{#if fireError}<p class="text-error-500 mt-2 text-sm">{fireError}</p>{/if}

<Modal open={firePickerCommand !== null} onClose={() => (firePickerCommand = null)}>
  <h2 class="h4 mb-1">Send from which ESP?</h2>
  <p class="text-surface-600-400 mb-4 text-sm">
    Choose the device to transmit "{firePickerCommand?.name}" from.
  </p>
  <DevicePicker devices={firePickerDevices} selectedId={null} onSelect={handleDevicePicked} />
</Modal>

<Modal open={deleteConfirmCommand !== null} onClose={() => (deleteConfirmCommand = null)}>
  <h2 class="h4 mb-1">Delete "{deleteConfirmCommand?.name}"?</h2>
  <p class="text-surface-600-400 mb-4 text-sm">This can't be undone -- you'll need to re-record it to get it back.</p>
  {#if deleteError}<p class="text-error-500 mb-2 text-sm">{deleteError}</p>{/if}
  <div class="flex justify-end gap-2">
    <button
      type="button"
      class="btn preset-tonal"
      disabled={deleteBusy}
      onclick={() => (deleteConfirmCommand = null)}
    >
      Cancel
    </button>
    <button
      type="button"
      class="btn preset-filled-error-500"
      disabled={deleteBusy}
      onclick={handleDeleteConfirmed}
    >
      Delete
    </button>
  </div>
</Modal>
