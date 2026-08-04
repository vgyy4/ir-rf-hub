<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import CommandList from "./lib/components/CommandList.svelte";
  import RecordModal from "./lib/components/modal/RecordModal.svelte";
  import EditModal from "./lib/components/modal/EditModal.svelte";
  import RawEditor from "./lib/components/modal/RawEditor.svelte";
  import { commandsStore } from "./lib/stores/commands.svelte";
  import { devicesStore } from "./lib/stores/devices.svelte";
  import { recordingWizard } from "./lib/stores/recording.svelte";
  import { editWizard } from "./lib/stores/edit.svelte";
  import type { CommandSummary } from "./lib/api";

  onMount(() => {
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

<main>
  <header class="app-header">
    <h1>IR/RF Command Hub</h1>
    <button type="button" class="new-recording" onclick={openRecordModal}>+ New Recording</button>
  </header>

  <CommandList onEdit={openEditModal} />
</main>

<RecordModal />
<EditModal />
<RawEditor />

<style>
  main {
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
    max-width: 640px;
    margin: 0 auto;
    padding: 1.5rem 1rem 3rem;
    color: #e6e6e6;
    min-height: 100vh;
    box-sizing: border-box;
  }

  .app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  h1 {
    font-size: 1.3rem;
    margin: 0;
  }

  .new-recording {
    padding: 0.6rem 1rem;
    border-radius: 8px;
    border: none;
    background: #2f81f7;
    color: white;
    font-size: 0.9rem;
    cursor: pointer;
  }

  @media (prefers-color-scheme: light) {
    main {
      color: #1a1a1a;
    }
  }
</style>
