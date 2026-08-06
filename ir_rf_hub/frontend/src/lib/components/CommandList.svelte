<script lang="ts">
  import CommandRow from "./CommandRow.svelte";
  import Modal from "./modal/Modal.svelte";
  import DevicePicker from "./DevicePicker.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Skeleton } from "$lib/components/ui/skeleton/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import * as AlertDialog from "$lib/components/ui/alert-dialog/index.js";
  import { commandsStore } from "../stores/commands.svelte";
  import { haptics } from "../haptics";
  import {
    candidateDevicesForCommand,
    deleteCommand,
    fireCommand,
    type CommandSummary,
    type EspDeviceSummary,
  } from "../api";
  import RadioTowerIcon from "@lucide/svelte/icons/radio-tower";

  interface Props {
    onEdit: (command: CommandSummary) => void;
  }

  let { onEdit }: Props = $props();

  let firePickerCommand = $state<CommandSummary | null>(null);
  let firePickerDevices = $state<EspDeviceSummary[]>([]);
  let fireError = $state<string | null>(null);

  // Which row just fired successfully, for the confirmation pulse. Paired with
  // haptics.success() so the send is acknowledged by both feel and sight --
  // previously a successful fire gave no feedback whatsoever.
  let firedId = $state<string | null>(null);
  let firedTimer: ReturnType<typeof setTimeout> | undefined;

  function markFired(id: string) {
    haptics.success();
    firedId = id;
    clearTimeout(firedTimer);
    firedTimer = setTimeout(() => (firedId = null), 600);
  }

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
      haptics.success();
    } catch (e) {
      deleteError = String(e);
      haptics.error();
    } finally {
      deleteBusy = false;
    }
  }

  async function handleFire(command: CommandSummary) {
    fireError = null;
    haptics.tap();
    if (command.default_device_id) {
      try {
        await fireCommand(command.id);
        markFired(command.id);
      } catch (e) {
        fireError = String(e);
        haptics.error();
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
    const id = firePickerCommand.id;
    try {
      await fireCommand(id, deviceId);
      markFired(id);
    } catch (e) {
      fireError = String(e);
      haptics.error();
    } finally {
      firePickerCommand = null;
    }
  }
</script>

{#if commandsStore.loading && commandsStore.items.length === 0}
  <ul class="flex flex-col gap-2" aria-label="Loading commands">
    {#each [0, 1, 2] as i (i)}
      <li class="bg-card border-border flex items-center gap-3 rounded-xl border p-4">
        <Skeleton class="h-5 w-9 rounded-full" />
        <Skeleton class="h-4 flex-1 max-w-40" />
      </li>
    {/each}
  </ul>
{:else if commandsStore.items.length === 0}
  <div
    class="border-border flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center"
  >
    <!-- Idle antenna, quietly listening for a first recording. -->
    <span class="relative flex size-12 items-center justify-center">
      <span
        class="bg-primary/15 motion-safe:animate-ping absolute inline-flex size-12 rounded-full opacity-75"
      ></span>
      <span class="bg-primary/15 text-primary relative rounded-full p-3">
        <RadioTowerIcon class="size-6" />
      </span>
    </span>
    <div class="space-y-1">
      <p class="font-medium">Nothing on the airwaves yet</p>
      <p class="text-muted-foreground text-sm">
        Point a remote at an ESP and hit "New Recording" to capture your first IR or RF command.
      </p>
    </div>
  </div>
{:else}
  <ul class="flex flex-col gap-2">
    {#each commandsStore.items as command (command.id)}
      <CommandRow
        {command}
        fired={firedId === command.id}
        onFire={handleFire}
        {onEdit}
        onDelete={handleDeleteRequest}
      />
    {/each}
  </ul>
{/if}

{#if fireError}
  <Alert.Root variant="destructive" class="mt-3">
    <Alert.Description>{fireError}</Alert.Description>
  </Alert.Root>
{/if}

<Modal open={firePickerCommand !== null} onClose={() => (firePickerCommand = null)}>
  <h2 class="mb-1 text-lg font-semibold tracking-tight">Send from which ESP?</h2>
  <p class="text-muted-foreground mb-4 text-sm">
    Choose the device to transmit "{firePickerCommand?.name}" from.
  </p>
  <DevicePicker devices={firePickerDevices} selectedId={null} onSelect={handleDevicePicked} />
</Modal>

<AlertDialog.Root
  open={deleteConfirmCommand !== null}
  onOpenChange={(next) => {
    if (!next) deleteConfirmCommand = null;
  }}
>
  <AlertDialog.Content>
    <AlertDialog.Header>
      <AlertDialog.Title>Delete "{deleteConfirmCommand?.name}"?</AlertDialog.Title>
      <AlertDialog.Description>
        This can't be undone -- you'll need to re-record it to get it back.
      </AlertDialog.Description>
    </AlertDialog.Header>
    {#if deleteError}
      <Alert.Root variant="destructive">
        <Alert.Description>{deleteError}</Alert.Description>
      </Alert.Root>
    {/if}
    <AlertDialog.Footer>
      <AlertDialog.Cancel disabled={deleteBusy}>Cancel</AlertDialog.Cancel>
      <!-- A plain Button rather than AlertDialog.Action: Action auto-closes on
           click, which would swallow the error message when a delete fails. -->
      <Button variant="destructive" disabled={deleteBusy} onclick={handleDeleteConfirmed}>
        Delete
      </Button>
    </AlertDialog.Footer>
  </AlertDialog.Content>
</AlertDialog.Root>
