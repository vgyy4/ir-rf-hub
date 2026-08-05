<script lang="ts">
  import Modal from "./Modal.svelte";
  import { editWizard } from "../../stores/edit.svelte";
  import { autofocus } from "../../actions";

  const wizard = editWizard;

  function cancel() {
    wizard.close();
  }
</script>

<Modal open={wizard.step === "raw-editor"} onClose={cancel} fullscreen>
  <div class="flex h-full flex-col">
    <header class="mb-4">
      <h2 class="h4 mb-1">Alter command &mdash; {wizard.command?.name}</h2>
      <p class="text-surface-600-400 text-sm">
        Comma-separated raw timings in microseconds. Positive = mark (on), negative = space (off) --
        the same format the device recorded.
      </p>
    </header>

    <textarea
      class="min-h-0 flex-1 resize-none rounded-lg bg-neutral-950 p-4 font-mono text-sm text-green-400 outline-none"
      bind:value={wizard.rawTimingsText}
      spellcheck="false"
    ></textarea>

    <label class="mt-3 block">
      <span class="text-surface-600-400 text-sm">Repeat count</span>
      <input type="number" class="input mt-1 w-32" min="1" bind:value={wizard.repeatCount} />
    </label>

    {#if wizard.error}<p class="text-error-500 mt-3 text-sm">{wizard.error}</p>{/if}

    {#if wizard.showSaveAsNewPrompt}
      <div class="mt-4 flex items-center gap-2">
        <input type="text" class="input flex-1" placeholder="New command name" bind:value={wizard.newCommandName} use:autofocus />
        <button type="button" class="btn preset-tonal" onclick={() => (wizard.showSaveAsNewPrompt = false)}>
          Back
        </button>
        <button
          type="button"
          class="btn preset-filled-primary-500"
          disabled={!wizard.newCommandName.trim() || wizard.busy}
          onclick={() => wizard.saveAsNewCommand()}
        >
          Confirm
        </button>
      </div>
    {:else}
      <div class="mt-4 flex justify-end gap-2">
        <button type="button" class="btn preset-tonal" onclick={cancel}>Cancel</button>
        <button
          type="button"
          class="btn preset-tonal"
          disabled={wizard.busy}
          onclick={() => (wizard.showSaveAsNewPrompt = true)}
        >
          Save to a new command
        </button>
        <button type="button" class="btn preset-filled-primary-500" disabled={wizard.busy} onclick={() => wizard.saveEdited()}>
          Save
        </button>
      </div>
    {/if}
  </div>
</Modal>
