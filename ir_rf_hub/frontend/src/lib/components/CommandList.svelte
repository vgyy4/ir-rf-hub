<script lang="ts">
  import CommandRow from "./CommandRow.svelte";
  import Modal from "./modal/Modal.svelte";
  import DevicePicker from "./DevicePicker.svelte";
  import { commandsStore } from "../stores/commands.svelte";
  import { candidateDevicesForCommand, fireCommand, type CommandSummary, type EspDeviceSummary } from "../api";

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
  <p class="hint">Loading&hellip;</p>
{:else if commandsStore.items.length === 0}
  <p class="hint">No recordings yet. Tap "New Recording" to capture your first IR or RF command.</p>
{:else}
  <ul class="list">
    {#each commandsStore.items as command (command.id)}
      <CommandRow {command} onFire={handleFire} {onEdit} />
    {/each}
  </ul>
{/if}

{#if fireError}<p class="error">{fireError}</p>{/if}

<Modal open={firePickerCommand !== null} onClose={() => (firePickerCommand = null)}>
  <h2>Send from which ESP?</h2>
  <p class="hint">Choose the device to transmit "{firePickerCommand?.name}" from.</p>
  <DevicePicker devices={firePickerDevices} selectedId={null} onSelect={handleDevicePicked} />
</Modal>

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .hint {
    color: #9aa4b2;
    font-size: 0.9rem;
  }

  .error {
    color: #ff6b6b;
    font-size: 0.85rem;
  }

  h2 {
    margin: 0 0 0.25rem;
  }
</style>
