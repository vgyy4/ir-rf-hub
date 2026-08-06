<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import CommandList from "./lib/components/CommandList.svelte";
  import RecordModal from "./lib/components/modal/RecordModal.svelte";
  import EditModal from "./lib/components/modal/EditModal.svelte";
  import RawEditor from "./lib/components/modal/RawEditor.svelte";
  import DevicesModal from "./lib/components/modal/DevicesModal.svelte";
  import PairingGate from "./lib/components/PairingGate.svelte";
  import { commandsStore } from "./lib/stores/commands.svelte";
  import { devicesStore } from "./lib/stores/devices.svelte";
  import { recordingWizard } from "./lib/stores/recording.svelte";
  import { editWizard } from "./lib/stores/edit.svelte";
  import { themeStore, type ThemeMode } from "./lib/stores/theme.svelte";
  import { getPairingStatus, type CommandSummary } from "./lib/api";
  import RadioTowerIcon from "@lucide/svelte/icons/radio-tower";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import RouterIcon from "@lucide/svelte/icons/router";

  let devicesModalOpen = $state(false);

  type GateState = "checking" | "unpaired" | "paired";

  let gateState = $state<GateState>("checking");
  let pairingCode = $state<string | null>(null);

  async function checkPairing() {
    const status = await getPairingStatus();
    if (status.paired) {
      gateState = "paired";
    } else {
      pairingCode = status.code;
      gateState = "unpaired";
    }
  }

  function onPaired() {
    gateState = "paired";
  }

  onMount(() => {
    void checkPairing();
  });

  $effect(() => {
    if (gateState !== "paired") return;
    void commandsStore.refresh();
    void devicesStore.refresh();
    commandsStore.startLiveSync();
  });

  onDestroy(() => {
    commandsStore.stopLiveSync();
  });

  function openRecordModal() {
    void devicesStore.refresh();
    recordingWizard.open();
  }

  function openEditModal(command: CommandSummary) {
    void devicesStore.refresh();
    void editWizard.open(command);
  }
</script>

<!-- Fixed full-viewport background: a soft radial glow over the theme's
     surface tone, well above HA's/the browser's own flat gray. Sits behind
     everything else at z-0, content scrolls independently above it. -->
<div class="bg-surface-50-950 fixed inset-0 -z-10">
  <div
    class="from-primary-500/20 via-secondary-500/10 absolute inset-0 bg-linear-to-br to-transparent"
  ></div>
  <div
    class="bg-primary-500/20 absolute -top-32 -left-32 size-96 rounded-full blur-3xl"
  ></div>
  <div
    class="bg-tertiary-500/20 absolute -right-32 -bottom-32 size-96 rounded-full blur-3xl"
  ></div>
</div>

{#if gateState === "unpaired" && pairingCode}
  <PairingGate code={pairingCode} {onPaired} />
{:else if gateState === "paired"}
  <div class="mx-auto min-h-screen max-w-2xl px-4 pt-6 pb-16">
    <header class="mb-6 flex items-center justify-between">
      <div class="flex items-center gap-2.5">
        <div class="bg-primary-500/15 text-primary-500 rounded-lg p-2">
          <RadioTowerIcon class="size-5" />
        </div>
        <h1 class="h4">IR/RF Command Hub</h1>
      </div>
      <div class="flex items-center gap-2">
        <select
          class="select w-auto text-sm"
          aria-label="Color theme"
          value={themeStore.mode}
          onchange={(e) => themeStore.setMode(e.currentTarget.value as ThemeMode)}
        >
          <option value="auto">Auto (HA)</option>
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>
        <button
          type="button"
          class="btn preset-tonal"
          aria-label="Manage ESPHome devices"
          onclick={() => (devicesModalOpen = true)}
        >
          <RouterIcon class="size-4" />
          Devices
        </button>
        <button type="button" class="btn preset-filled-primary-500" onclick={openRecordModal}>
          <PlusIcon class="size-4" />
          New Recording
        </button>
      </div>
    </header>

    <CommandList onEdit={openEditModal} />
  </div>

  <RecordModal />
  <EditModal />
  <RawEditor />
  <DevicesModal open={devicesModalOpen} onClose={() => (devicesModalOpen = false)} />
{/if}
