<script lang="ts">
  import Modal from "./Modal.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { createDevice, deleteDevice, discoverDevices, type DiscoveredDevice } from "../../api";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";
  import RadarIcon from "@lucide/svelte/icons/radar";

  interface Props {
    open: boolean;
    onClose: () => void;
  }

  let { open, onClose }: Props = $props();

  let showAddForm = $state(false);
  let name = $state("");
  let host = $state("");
  let port = $state(6053);
  let encryptionKey = $state("");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let discovered = $state<DiscoveredDevice[]>([]);
  let discovering = $state(false);

  $effect(() => {
    if (open) void devicesStore.refresh();
  });

  async function handleDiscover() {
    discovering = true;
    try {
      discovered = await discoverDevices();
    } catch {
      discovered = [];
    } finally {
      discovering = false;
    }
  }

  function pickDiscovered(d: DiscoveredDevice) {
    name = d.name;
    host = d.host;
    port = d.port;
    showAddForm = true;
    discovered = [];
  }

  function resetForm() {
    name = "";
    host = "";
    port = 6053;
    encryptionKey = "";
    showAddForm = false;
    error = null;
  }

  async function handleAdd() {
    if (!name.trim() || !host.trim()) return;
    busy = true;
    error = null;
    try {
      await createDevice({
        name: name.trim(),
        host: host.trim(),
        port,
        encryption_key: encryptionKey.trim() || null,
      });
      resetForm();
      await devicesStore.refresh();
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function handleDelete(id: string) {
    await deleteDevice(id);
    await devicesStore.refresh();
  }
</script>

<Modal {open} {onClose}>
  <div class="mb-4 flex items-center justify-between">
    <h2 class="h4">ESPHome Devices</h2>
    <button
      type="button"
      class="btn-icon preset-tonal"
      onclick={handleDiscover}
      aria-label="Scan for devices on your network"
    >
      <RadarIcon class={["size-4", discovering && "animate-spin"]} />
    </button>
  </div>

  {#if discovered.length > 0}
    <div class="mb-3 space-y-1.5">
      <p class="text-surface-500 text-xs tracking-wide uppercase">Found on your network</p>
      {#each discovered as d (d.host + d.port)}
        <button
          type="button"
          class="card preset-tonal-primary hover:preset-filled-primary-500 w-full p-2.5 text-left text-sm transition-colors"
          onclick={() => pickDiscovered(d)}
        >
          {d.name} <span class="opacity-60">({d.host}:{d.port})</span>
        </button>
      {/each}
    </div>
  {/if}

  <ul class="mb-3 flex max-h-64 flex-col gap-2 overflow-y-auto">
    {#each devicesStore.items as device (device.id)}
      <li class="card preset-filled-surface-100-900 flex items-center justify-between gap-2 p-3">
        <div class="min-w-0">
          <p class="truncate font-medium">{device.name}</p>
          <p class="text-surface-500 text-xs">
            {device.host}:{device.port} &middot; {device.entities.length} entit{device.entities
              .length === 1
              ? "y"
              : "ies"}
          </p>
        </div>
        <button
          type="button"
          class="btn-icon hover:preset-tonal-error shrink-0"
          aria-label="Remove {device.name}"
          onclick={() => handleDelete(device.id)}
        >
          <Trash2Icon class="size-4" />
        </button>
      </li>
    {:else}
      <p class="text-surface-500 text-sm italic">No devices added yet.</p>
    {/each}
  </ul>

  {#if showAddForm}
    <div class="card preset-filled-surface-100-900 space-y-2 p-3">
      <input class="input" placeholder="Name" bind:value={name} />
      <input class="input" placeholder="Host (IP or .local)" bind:value={host} />
      <input class="input" type="number" placeholder="Port" bind:value={port} />
      <input class="input" placeholder="Encryption key (optional)" bind:value={encryptionKey} />
      {#if error}<p class="text-error-500 text-xs">{error}</p>{/if}
      <div class="flex justify-end gap-2">
        <button type="button" class="btn preset-tonal btn-sm" onclick={resetForm}>Cancel</button>
        <button
          type="button"
          class="btn preset-filled-primary-500 btn-sm"
          disabled={busy || !name.trim() || !host.trim()}
          onclick={handleAdd}
        >
          Add
        </button>
      </div>
    </div>
  {:else}
    <button type="button" class="btn preset-tonal w-full" onclick={() => (showAddForm = true)}>
      <PlusIcon class="size-4" />
      Add device manually
    </button>
  {/if}
</Modal>
