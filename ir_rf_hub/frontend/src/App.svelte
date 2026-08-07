<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import CommandList from "./lib/components/CommandList.svelte";
  import RecordModal from "./lib/components/modal/RecordModal.svelte";
  import EditModal from "./lib/components/modal/EditModal.svelte";
  import RawEditor from "./lib/components/modal/RawEditor.svelte";
  import DevicesModal from "./lib/components/modal/DevicesModal.svelte";
  import SearchModal from "./lib/components/modal/SearchModal.svelte";
  import PairingGate from "./lib/components/PairingGate.svelte";
  import ThemeMenu from "./lib/components/ThemeMenu.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { commandsStore } from "./lib/stores/commands.svelte";
  import { devicesStore } from "./lib/stores/devices.svelte";
  import { recordingWizard } from "./lib/stores/recording.svelte";
  import { editWizard } from "./lib/stores/edit.svelte";
  import { searchWizard } from "./lib/stores/search.svelte";
  import { getPairingStatus, type CommandSummary } from "./lib/api";
  import RadioTowerIcon from "@lucide/svelte/icons/radio-tower";
  import PlusIcon from "@lucide/svelte/icons/plus";
  import RouterIcon from "@lucide/svelte/icons/router";
  import SearchIcon from "@lucide/svelte/icons/search";

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

  function openSearchModal() {
    void devicesStore.refresh();
    searchWizard.open();
  }

  function openEditModal(command: CommandSummary) {
    void devicesStore.refresh();
    void editWizard.open(command);
  }
</script>

<!-- Fixed full-viewport background: a soft accent glow over the theme's own
     background tone, well above HA's/the browser's flat gray. Deliberately
     restrained now that the chrome is neutral -- it should register as warmth
     in the corners, not as a coloured page. Catppuccin keeps a stronger wash,
     since that palette is opted into for exactly that character. Sits behind
     everything at -z-10; content scrolls independently above it. -->
<div class="bg-background fixed inset-0 -z-10">
  <div
    class="from-glow-1/10 via-glow-2/5 absolute inset-0 bg-linear-to-br to-transparent in-data-[theme=catppuccin]:from-glow-1/20 in-data-[theme=catppuccin]:via-glow-2/10"
  ></div>
  <div
    class="bg-glow-1/15 in-data-[theme=catppuccin]:bg-glow-1/25 absolute -top-32 -left-32 size-96 rounded-full blur-3xl"
  ></div>
  <div
    class="bg-glow-2/15 in-data-[theme=catppuccin]:bg-glow-2/25 absolute -right-32 -bottom-32 size-96 rounded-full blur-3xl"
  ></div>
</div>

{#if gateState === "unpaired" && pairingCode}
  <PairingGate code={pairingCode} {onPaired} />
{:else if gateState === "paired"}
  <div class="mx-auto min-h-screen max-w-2xl px-4 pt-6 pb-16">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-x-2 gap-y-3">
      <div class="flex shrink-0 items-center gap-2.5">
        <div class="bg-primary/15 text-primary rounded-lg p-2">
          <RadioTowerIcon class="size-5" />
        </div>
        <h1 class="text-lg font-semibold tracking-tight whitespace-nowrap">IR/RF Hub</h1>
      </div>
      <div class="flex items-center gap-1.5 sm:gap-2">
        <ThemeMenu />
        <Button
          variant="secondary"
          aria-label="Manage ESPHome devices"
          onclick={() => (devicesModalOpen = true)}
        >
          <RouterIcon />
          <span class="hidden sm:inline">Devices</span>
        </Button>
        <Button variant="secondary" aria-label="Search for a known remote's command" onclick={openSearchModal}>
          <SearchIcon />
          <span class="hidden sm:inline">Search</span>
        </Button>
        <Button onclick={openRecordModal} aria-label="New Recording">
          <PlusIcon />
          <span class="hidden sm:inline">New Recording</span>
        </Button>
      </div>
    </header>

    <CommandList onEdit={openEditModal} />
  </div>

  <RecordModal />
  <EditModal />
  <RawEditor />
  <SearchModal />
  <DevicesModal open={devicesModalOpen} onClose={() => (devicesModalOpen = false)} />
{/if}
