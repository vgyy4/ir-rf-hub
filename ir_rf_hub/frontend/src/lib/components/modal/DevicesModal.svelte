<script lang="ts">
  import Modal from "./Modal.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { createDevice, deleteDevice, discoverDevices, testDevice, type DiscoveredDevice } from "../../api";
  import { copyElementText } from "../../clipboard";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";
  import RadarIcon from "@lucide/svelte/icons/radar";
  import CopyIcon from "@lucide/svelte/icons/copy";
  import CheckIcon from "@lucide/svelte/icons/check";
  import RefreshCwIcon from "@lucide/svelte/icons/refresh-cw";

  // Matches DevicePicker.svelte's convention for "reachable enough to
  // treat as online" -- anything mid-transmit/receive still counts.
  const ONLINE_STATES = new Set(["idle", "rx_active", "tx_active", "rx_settling", "tx_settling"]);

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

  // Set right after a device is successfully added, and shown once as a
  // tip -- not gating the Add itself (that was an extra click on every
  // single add, forever) and not repeated every time the menu reopens
  // (that kept nagging about devices you'd already sorted out). Cleared
  // on dismiss, on starting another add, or on closing the modal.
  let justAdded = $state<{ name: string; host: string } | null>(null);

  function ipv4Octets(value: string): number[] | null {
    const parts = value.trim().split(".");
    if (parts.length !== 4) return null;
    const octets = parts.map(Number);
    if (octets.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return null;
    return octets;
  }

  // Neither the App nor the browser can see the user's actual router
  // config, so this is only ever a generic suggestion -- gateway-at-.1
  // and a /24 subnet are just the overwhelming convention for home
  // networks, not something read from the network. Only computable when
  // the host is a literal IPv4 address (a .local hostname has no IP to
  // derive a gateway/subnet from).
  let justAddedYaml = $derived.by(() => {
    if (!justAdded) return null;
    const octets = ipv4Octets(justAdded.host);
    if (!octets) return null;
    const gateway = `${octets[0]}.${octets[1]}.${octets[2]}.1`;
    return (
      `wifi:\n` +
      `  manual_ip:\n` +
      `    static_ip: ${justAdded.host}\n` +
      `    gateway: ${gateway}\n` +
      `    subnet: 255.255.255.0`
    );
  });

  let yamlEl: HTMLElement | undefined = $state();
  let yamlCopied = $state(false);

  async function copyYaml() {
    if (!yamlEl || !justAddedYaml || !(await copyElementText(yamlEl, justAddedYaml))) return;
    yamlCopied = true;
    setTimeout(() => (yamlCopied = false), 2000);
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
      testError = null;
      justAdded = null;
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
    justAdded = null;
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
      const created = await createDevice({
        name: name.trim(),
        host: host.trim(),
        port,
        encryption_key: encryptionKey.trim() || null,
      });
      justAdded = { name: created.name, host: created.host };
      yamlCopied = false;
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

  let testingDeviceId = $state<string | null>(null);
  let testError = $state<{ id: string; message: string } | null>(null);

  // Forces a fresh reconnect + entity re-scan on demand -- what to use
  // right after e.g. reflashing an ESP with new IR/RF hardware, rather
  // than waiting for the App to happen to notice on its own (it only
  // reconnects at startup or when something else needs the device).
  async function handleTest(id: string) {
    testingDeviceId = id;
    testError = null;
    try {
      await testDevice(id);
      await devicesStore.refresh();
    } catch (e) {
      testError = { id, message: String(e) };
    } finally {
      testingDeviceId = null;
    }
  }
</script>

<Modal {open} {onClose}>
  <div class="mb-4 flex items-center justify-between">
    <h2 class="h4">ESPHome Devices</h2>
    <button
      type="button"
      class="btn preset-tonal btn-sm"
      onclick={handleDiscover}
      aria-label="Scan for devices on your network"
    >
      <RadarIcon class={["size-4", discovering && "animate-spin"]} />
      Scan for devices
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

  {#if justAdded}
    <div class="card preset-tonal-primary mb-3 space-y-2 p-3 text-xs">
      <p class="font-medium">{justAdded.name} added.</p>
      {#if justAddedYaml}
        <p>
          If you haven't already, it's worth giving it a static IP so the App doesn't lose it after a
          reboot or router restart. Add this to the <code>wifi:</code> section of its ESPHome YAML --
          double-check the gateway and subnet against your own router, these are just the most common
          home-network defaults, not read from your network:
        </p>
        <div class="border-surface-300-700 bg-surface-50-950 overflow-x-auto rounded-lg border p-3">
          <pre bind:this={yamlEl} class="font-mono text-xs whitespace-pre">{justAddedYaml}</pre>
        </div>
        <button type="button" class="btn preset-tonal btn-sm w-full" onclick={copyYaml}>
          {#if yamlCopied}
            <CheckIcon class="size-4" />
            Copied
          {:else}
            <CopyIcon class="size-4" />
            Copy YAML
          {/if}
        </button>
      {:else}
        <p>
          If you haven't already, it's worth giving {justAdded.host} an actual static IP for the most
          reliable setup -- either a DHCP reservation on your router, or a <code>manual_ip:</code> block
          under <code>wifi:</code> in its ESPHome YAML -- since hostname (mDNS) resolution isn't always
          reliable for this App.
        </p>
      {/if}
      <button type="button" class="btn preset-tonal btn-sm w-full" onclick={() => (justAdded = null)}>
        Dismiss
      </button>
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
            &middot;
            <span
              class={[
                "tracking-wide uppercase",
                ONLINE_STATES.has(device.connection_state) ? "text-success-500" : "text-surface-500",
              ]}
            >
              {device.connection_state}
            </span>
          </p>
          {#if testError?.id === device.id}
            <p class="text-error-500 mt-1 text-xs">{testError.message}</p>
          {/if}
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <button
            type="button"
            class="btn-icon preset-tonal"
            aria-label="Test connection to {device.name}"
            disabled={testingDeviceId === device.id}
            onclick={() => handleTest(device.id)}
          >
            <RefreshCwIcon class={["size-4", testingDeviceId === device.id && "animate-spin"]} />
          </button>
          <button
            type="button"
            class="btn-icon hover:preset-tonal-error"
            aria-label="Remove {device.name}"
            onclick={() => handleDelete(device.id)}
          >
            <Trash2Icon class="size-4" />
          </button>
        </div>
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
    <button
      type="button"
      class="btn preset-tonal w-full"
      onclick={() => {
        showAddForm = true;
        justAdded = null;
      }}
    >
      <PlusIcon class="size-4" />
      Add device manually
    </button>
  {/if}
</Modal>
