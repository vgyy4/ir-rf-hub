<script lang="ts">
  import Modal from "./Modal.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import { Skeleton } from "$lib/components/ui/skeleton/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import * as AlertDialog from "$lib/components/ui/alert-dialog/index.js";
  import { devicesStore } from "../../stores/devices.svelte";
  import {
    createDevice,
    deleteDevice,
    discoverDevices,
    getHostNetwork,
    testDevice,
    updateDevice,
    type DiscoveredDevice,
    type EspDeviceSummary,
    type HostNetwork,
    type UpdateDeviceRequest,
  } from "../../api";
  import { copyElementText } from "../../clipboard";
  import { haptics } from "../../haptics";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import RadarIcon from "@lucide/svelte/icons/radar";
  import CopyIcon from "@lucide/svelte/icons/copy";
  import CheckIcon from "@lucide/svelte/icons/check";
  import RefreshCwIcon from "@lucide/svelte/icons/refresh-cw";
  import InfoIcon from "@lucide/svelte/icons/info";

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
  let password = $state("");
  let busy = $state(false);
  let error = $state<string | null>(null);
  let discovered = $state<DiscoveredDevice[]>([]);
  let discovering = $state(false);

  let deleteConfirmDevice = $state<EspDeviceSummary | null>(null);
  let deleteBusy = $state(false);
  let deleteError = $state<string | null>(null);

  let editingDevice = $state<EspDeviceSummary | null>(null);
  let editName = $state("");
  let editHost = $state("");
  let editPort = $state(6053);
  let editEncryptionKey = $state("");
  let editPassword = $state("");
  let editTxSettleMs = $state(150);
  let editRxStopSettleMs = $state(150);
  let editConnectTimeoutS = $state(10);
  let editBusy = $state(false);
  let editError = $state<string | null>(null);

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

  // The host's real gateway and subnet, read from Supervisor (see the
  // backend's supervisor_network.py). Fetched once when the menu opens.
  // `guessed` means Supervisor wasn't reachable and we're back to the old
  // convention -- the copy below says so rather than stating it as fact.
  let hostNetwork = $state<HostNetwork | null>(null);

  // Only computable when the host is a literal IPv4 address (a .local
  // hostname has no IP to build a manual_ip block around).
  let justAddedYaml = $derived.by(() => {
    if (!justAdded) return null;
    const octets = ipv4Octets(justAdded.host);
    if (!octets) return null;
    // Convention fallback: gateway at .1, /24. Only used when Supervisor
    // couldn't tell us the real values.
    const gateway = hostNetwork?.gateway || `${octets[0]}.${octets[1]}.${octets[2]}.1`;
    const subnet = hostNetwork?.subnet_mask || "255.255.255.0";
    return (
      `wifi:\n` +
      `  manual_ip:\n` +
      `    static_ip: ${justAdded.host}\n` +
      `    gateway: ${gateway}\n` +
      `    subnet: ${subnet}`
    );
  });

  let yamlEl: HTMLElement | undefined = $state();
  let yamlCopied = $state(false);

  async function copyYaml() {
    if (!yamlEl || !justAddedYaml || !(await copyElementText(yamlEl, justAddedYaml))) return;
    yamlCopied = true;
    haptics.success();
    setTimeout(() => (yamlCopied = false), 2000);
  }

  $effect(() => {
    if (open) {
      void devicesStore.refresh();
      // Cheap, and only meaningful once a device is actually added -- but
      // fetching it here means the tip renders complete rather than
      // filling in its gateway/subnet a beat later.
      if (!hostNetwork) void getHostNetwork().then((n) => (hostNetwork = n)).catch(() => {});
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
      deleteConfirmDevice = null;
      editingDevice = null;
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
    haptics.tap();
    name = d.name;
    host = d.host;
    port = d.port;
    showAddForm = true;
    discovered = [];
    justAdded = null;
    editingDevice = null;
  }

  function resetForm() {
    name = "";
    host = "";
    port = 6053;
    encryptionKey = "";
    password = "";
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
        password: password.trim() || null,
      });
      justAdded = { name: created.name, host: created.host };
      yamlCopied = false;
      resetForm();
      await devicesStore.refresh();
      haptics.success();
    } catch (e) {
      error = String(e);
      haptics.error();
    } finally {
      busy = false;
    }
  }

  function handleDeleteRequest(device: EspDeviceSummary) {
    haptics.tap();
    deleteError = null;
    deleteConfirmDevice = device;
  }

  async function handleDeleteConfirmed() {
    if (!deleteConfirmDevice) return;
    deleteBusy = true;
    deleteError = null;
    try {
      await deleteDevice(deleteConfirmDevice.id);
      await devicesStore.refresh();
      deleteConfirmDevice = null;
      haptics.success();
    } catch (e) {
      deleteError = String(e);
      haptics.error();
    } finally {
      deleteBusy = false;
    }
  }

  function openEdit(device: EspDeviceSummary) {
    haptics.tap();
    showAddForm = false;
    justAdded = null;
    editingDevice = device;
    editName = device.name;
    editHost = device.host;
    editPort = device.port;
    editEncryptionKey = "";
    editPassword = "";
    editTxSettleMs = device.tx_settle_ms;
    editRxStopSettleMs = device.rx_stop_settle_ms;
    editConnectTimeoutS = device.connect_timeout_s;
    editError = null;
  }

  function closeEdit() {
    editingDevice = null;
  }

  async function handleEditSave() {
    if (!editingDevice || !editName.trim() || !editHost.trim()) return;
    editBusy = true;
    editError = null;
    try {
      // encryption_key / password are only sent when the user actually typed
      // something -- an empty field means "leave the stored secret alone",
      // not "clear it" (the backend treats any key present in the request
      // body, even blank, as an explicit change).
      const payload: UpdateDeviceRequest = {
        name: editName.trim(),
        host: editHost.trim(),
        port: editPort,
        tx_settle_ms: editTxSettleMs,
        rx_stop_settle_ms: editRxStopSettleMs,
        connect_timeout_s: editConnectTimeoutS,
      };
      if (editEncryptionKey.trim()) payload.encryption_key = editEncryptionKey.trim();
      if (editPassword.trim()) payload.password = editPassword.trim();
      await updateDevice(editingDevice.id, payload);
      await devicesStore.refresh();
      editingDevice = null;
      haptics.success();
    } catch (e) {
      editError = String(e);
      haptics.error();
    } finally {
      editBusy = false;
    }
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
      haptics.success();
    } catch (e) {
      testError = { id, message: String(e) };
      haptics.error();
    } finally {
      testingDeviceId = null;
    }
  }
</script>

<Modal {open} {onClose}>
  <div class="mb-4 flex items-center justify-between gap-2">
    <h2 class="text-lg font-semibold tracking-tight">ESPHome Devices</h2>
    <Button
      variant="secondary"
      size="sm"
      class="mr-8"
      onclick={handleDiscover}
      aria-label="Scan for devices on your network"
    >
      <RadarIcon class={discovering ? "motion-safe:animate-spin" : undefined} />
      Scan for devices
    </Button>
  </div>

  <div class="text-muted-foreground bg-muted/40 border-border mb-3 flex items-start gap-2 rounded-lg border p-2.5 text-xs">
    <InfoIcon class="mt-0.5 size-3.5 shrink-0" />
    <p>
      Each device needs the <code>ir_rf_proxy</code> component in its ESPHome YAML, on top of a
      <code>remote_receiver</code>/<code>remote_transmitter</code> config -- it won't show up with any
      usable entities otherwise. See the
      <a
        class="text-foreground underline underline-offset-2"
        href="https://github.com/vgyy4/ir-rf-hub/blob/main/ir_rf_hub/DOCS.md"
        target="_blank"
        rel="noopener noreferrer"
      >
        Documentation tab or DOCS.md
      </a>
      for a copy-paste example.
    </p>
  </div>

  {#if discovered.length > 0}
    <div class="mb-3 space-y-1.5">
      <p class="text-muted-foreground text-xs tracking-wide uppercase">Found on your network</p>
      {#each discovered as d (d.host + d.port)}
        <button
          type="button"
          class="press border-primary/25 bg-primary/10 hover:bg-primary/20 focus-visible:border-ring focus-visible:ring-ring/50 w-full rounded-lg border p-2.5 text-left text-sm transition-colors outline-none focus-visible:ring-3"
          onclick={() => pickDiscovered(d)}
        >
          {d.name} <span class="opacity-60">({d.host}:{d.port})</span>
        </button>
      {/each}
    </div>
  {/if}

  {#if justAdded}
    <div class="bg-primary/10 border-primary/20 mb-3 space-y-2 rounded-lg border p-3 text-xs">
      <p class="font-medium">{justAdded.name} added.</p>
      {#if justAddedYaml}
        <p>
          If you haven't already, it's worth giving it a static IP so the App doesn't lose it after a
          reboot or router restart. Add this to the <code>wifi:</code> section of its ESPHome YAML{#if hostNetwork && !hostNetwork.guessed}
            -- the gateway and subnet are Home Assistant's own, so they're right as long as the ESP
            is on the same network:{:else}
            -- double-check the gateway and subnet against your own router, these are the most common
            home-network defaults rather than your actual values:{/if}
        </p>
        <div class="border-border bg-background overflow-x-auto rounded-lg border p-3">
          <pre bind:this={yamlEl} class="font-mono text-xs whitespace-pre">{justAddedYaml}</pre>
        </div>
        <Button variant="outline" size="sm" class="w-full" onclick={copyYaml}>
          {#if yamlCopied}
            <CheckIcon class="motion-safe:animate-in motion-safe:zoom-in-75 motion-safe:fade-in motion-safe:duration-500 motion-safe:ease-out" />
            Copied
          {:else}
            <CopyIcon />
            Copy YAML
          {/if}
        </Button>
      {:else}
        <p>
          If you haven't already, it's worth giving {justAdded.host} an actual static IP for the most
          reliable setup -- either a DHCP reservation on your router, or a <code>manual_ip:</code>
          block under <code>wifi:</code> in its ESPHome YAML -- since hostname (mDNS) resolution isn't
          always reliable for this App.
        </p>
      {/if}
      <Button variant="outline" size="sm" class="w-full" onclick={() => (justAdded = null)}>
        Dismiss
      </Button>
    </div>
  {/if}

  {#if devicesStore.loading && devicesStore.items.length === 0}
    <ul class="mb-3 flex flex-col gap-2" aria-label="Loading devices">
      {#each [0, 1] as i (i)}
        <li class="bg-card border-border flex items-center gap-3 rounded-lg border p-3">
          <Skeleton class="h-8 flex-1" />
        </li>
      {/each}
    </ul>
  {:else}
  <ul class="mb-3 flex max-h-64 flex-col gap-2 overflow-y-auto">
    {#each devicesStore.items as device (device.id)}
      <li class="bg-card border-border flex items-center justify-between gap-2 rounded-lg border p-3">
        <div class="min-w-0">
          <p class="truncate font-medium">{device.name}</p>
          <p class="text-muted-foreground text-xs">
            {device.host}:{device.port} &middot; {device.entities.length} entit{device.entities
              .length === 1
              ? "y"
              : "ies"}
            &middot;
            <span
              class={[
                "tracking-wide uppercase",
                ONLINE_STATES.has(device.connection_state) ? "text-success" : "text-muted-foreground",
              ]}
            >
              {device.connection_state}
            </span>
          </p>
          {#if testError?.id === device.id}
            <p class="text-destructive mt-1 text-xs">{testError.message}</p>
          {/if}
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Test connection to {device.name}"
            disabled={testingDeviceId === device.id}
            onclick={() => handleTest(device.id)}
          >
            <RefreshCwIcon
              class={testingDeviceId === device.id ? "motion-safe:animate-spin" : undefined}
            />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Edit {device.name}"
            onclick={() => openEdit(device)}
          >
            <PencilIcon />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            class="hover:text-destructive hover:bg-destructive/10"
            aria-label="Remove {device.name}"
            onclick={() => handleDeleteRequest(device)}
          >
            <Trash2Icon />
          </Button>
        </div>
      </li>
    {:else}
      <p class="text-muted-foreground text-sm italic">
        No devices added yet -- discover one above, or add one manually below. Remember it'll need
        <code>ir_rf_proxy</code> in its YAML first (see the note above).
      </p>
    {/each}
  </ul>
  {/if}

  {#if editingDevice}
    <div class="bg-card border-border space-y-2 rounded-lg border p-3">
      <p class="text-muted-foreground text-xs tracking-wide uppercase">Editing {editingDevice.name}</p>
      <Input placeholder="Name" bind:value={editName} />
      <Input placeholder="Host (IP or .local)" bind:value={editHost} />
      <Input type="number" placeholder="Port" bind:value={editPort} />
      <Input placeholder="Encryption key (leave blank to keep current)" bind:value={editEncryptionKey} />
      <Input placeholder="Password (leave blank to keep current)" bind:value={editPassword} />
      <div class="grid grid-cols-3 gap-2">
        <label class="space-y-1 text-xs">
          <span class="text-muted-foreground">TX settle (ms)</span>
          <Input type="number" bind:value={editTxSettleMs} />
        </label>
        <label class="space-y-1 text-xs">
          <span class="text-muted-foreground">RX settle (ms)</span>
          <Input type="number" bind:value={editRxStopSettleMs} />
        </label>
        <label class="space-y-1 text-xs">
          <span class="text-muted-foreground">Connect timeout (s)</span>
          <Input type="number" bind:value={editConnectTimeoutS} />
        </label>
      </div>
      {#if editError}
        <Alert.Root variant="destructive">
          <Alert.Description>{editError}</Alert.Description>
        </Alert.Root>
      {/if}
      <div class="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onclick={closeEdit}>Cancel</Button>
        <Button
          size="sm"
          disabled={editBusy || !editName.trim() || !editHost.trim()}
          onclick={handleEditSave}
        >
          Save
        </Button>
      </div>
    </div>
  {:else if showAddForm}
    <div class="bg-card border-border space-y-2 rounded-lg border p-3">
      <Input placeholder="Name" bind:value={name} />
      <Input placeholder="Host (IP or .local)" bind:value={host} />
      <Input type="number" placeholder="Port" bind:value={port} />
      <Input placeholder="Encryption key (only if this ESP uses one)" bind:value={encryptionKey} />
      <Input placeholder="Password (only if this ESP uses one)" bind:value={password} />
      {#if error}
        <Alert.Root variant="destructive">
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      {/if}
      <div class="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onclick={resetForm}>Cancel</Button>
        <Button size="sm" disabled={busy || !name.trim() || !host.trim()} onclick={handleAdd}>
          Add
        </Button>
      </div>
    </div>
  {:else}
    <Button
      variant="secondary"
      class="w-full"
      onclick={() => {
        showAddForm = true;
        justAdded = null;
      }}
    >
      <PlusIcon />
      Add device manually
    </Button>
  {/if}

  <AlertDialog.Root
    open={deleteConfirmDevice !== null}
    onOpenChange={(next) => {
      if (!next) deleteConfirmDevice = null;
    }}
  >
    <AlertDialog.Content>
      <AlertDialog.Header>
        <AlertDialog.Title>Remove "{deleteConfirmDevice?.name}"?</AlertDialog.Title>
        <AlertDialog.Description>
          This removes the device and its discovered entities from the App. Commands recorded from it
          stay in your library, but you'll need to re-add the device before you can fire or re-record
          through it.
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
          Remove
        </Button>
      </AlertDialog.Footer>
    </AlertDialog.Content>
  </AlertDialog.Root>
</Modal>
