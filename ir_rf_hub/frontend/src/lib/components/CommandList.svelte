<script lang="ts">
  import CommandRow from "./CommandRow.svelte";
  import Modal from "./modal/Modal.svelte";
  import DevicePicker from "./DevicePicker.svelte";
  import { commandsStore } from "../stores/commands.svelte";
  import { candidateDevicesForCommand, fireCommand, type CommandSummary, type EspDeviceSummary } from "../api";
  import InboxIcon from "@lucide/svelte/icons/inbox";

  interface Props {
    onEdit: (command: CommandSummary) => void;
  }

  let { onEdit }: Props = $props();

  let firePickerCommand = $state<CommandSummary | null>(null);
  let firePickerDevices = $state<EspDeviceSummary[]>([]);
  let fireError = $state<string | null>(null);

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
      <CommandRow {command} onFire={handleFire} {onEdit} />
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
