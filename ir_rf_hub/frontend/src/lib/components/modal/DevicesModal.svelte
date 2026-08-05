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

  // The App has no way to actually inspect an ESP's YAML (it only ever
  // talks to it over the native API), so this can't be a per-device
  // "detected" fact -- it's a standing recommendation, shown consistently
  // until the user dismisses it, rather than a check that passes or fails.
  const HIDE_STATIC_IP_TIP_KEY = "ir_rf_hub_hide_static_ip_tip";
  let hideStaticIpTip = $state(localStorage.getItem(HIDE_STATIC_IP_TIP_KEY) === "1");

  function setHideStaticIpTip(value: boolean) {
    hideStaticIpTip = value;
    localStorage.setItem(HIDE_STATIC_IP_TIP_KEY, value ? "1" : "0");
  }

  $effect(() => {
    if (open) {
      void devicesStore.refresh();
      // Saves the user a click in the common case (opening the menu to
      // add a device that's already powered on); the radar button stays
      // for the "opened the menu, then turned the ESP on" case this can't
      // cover.
      void handleDiscover();
    } else {
      // This component stays mounted across close/open (Modal just
      // toggles visibility), so without this the add-device form -- and
      // a stale discovered-devices list -- would still be showing the
      // next time the menu opens.
      resetForm();
      discovered = [];
    }
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

  {#if !hideStaticIpTip && devicesStore.items.length > 0}
    <p class="text-surface-500 mb-2 text-xs">
      Tip: give these ESPs a static IP (a router DHCP reservation, or <code>manual_ip:</code> in their
      ESPHome YAML) so the App doesn't lose them after a reboot.
    </p>
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
      <input class="input" placeholder="Encryption key (only if this ESP uses one)" bind:value={encryptionKey} />
      {#if !hideStaticIpTip}
        <div class="preset-tonal-warning space-y-2 rounded-lg p-2.5 text-xs">
          <p>
            <strong>Recommended:</strong> give this ESP a static IP -- either a DHCP reservation on your
            router, or a <code>manual_ip:</code> block under <code>wifi:</code> in its ESPHome YAML.
            Without one, its IP can change after a reboot or router restart, and the App will lose it
            until you update the host here manually.
          </p>
          <label class="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={hideStaticIpTip}
              onchange={(e) => setHideStaticIpTip(e.currentTarget.checked)}
            />
            <span>Don't show this again</span>
          </label>
        </div>
      {/if}
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
