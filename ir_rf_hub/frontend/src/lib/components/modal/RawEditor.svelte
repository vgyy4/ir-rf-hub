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
  <div class="editor">
    <header>
      <h2>Alter command &mdash; {wizard.command?.name}</h2>
      <p class="hint">
        Comma-separated raw timings in microseconds. Positive = mark (on), negative = space (off) --
        the same format the device recorded.
      </p>
    </header>

    <textarea class="raw-text" bind:value={wizard.rawTimingsText} spellcheck="false"></textarea>

    {#if wizard.error}<p class="error">{wizard.error}</p>{/if}

    {#if wizard.showSaveAsNewPrompt}
      <div class="save-as-new">
        <input
          type="text"
          placeholder="New command name"
          bind:value={wizard.newCommandName}
          use:autofocus
        />
        <button type="button" class="secondary" onclick={() => (wizard.showSaveAsNewPrompt = false)}>
          Back
        </button>
        <button
          type="button"
          disabled={!wizard.newCommandName.trim() || wizard.busy}
          onclick={() => wizard.saveAsNewCommand()}
        >
          Confirm
        </button>
      </div>
    {:else}
      <div class="actions">
        <button type="button" class="secondary" onclick={cancel}>Cancel</button>
        <button
          type="button"
          class="secondary"
          disabled={wizard.busy}
          onclick={() => (wizard.showSaveAsNewPrompt = true)}
        >
          Save to a new command
        </button>
        <button type="button" disabled={wizard.busy} onclick={() => wizard.saveEdited()}>Save</button>
      </div>
    {/if}
  </div>
</Modal>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  h2 {
    margin: 0 0 0.25rem;
  }

  .hint {
    color: #9aa4b2;
    font-size: 0.85rem;
    margin: 0 0 1rem;
  }

  .raw-text {
    flex: 1;
    width: 100%;
    box-sizing: border-box;
    resize: none;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size: 0.9rem;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #333944;
    background: #0c0e12;
    color: #7ee787;
  }

  .actions,
  .save-as-new {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 0.6rem;
    margin-top: 1rem;
  }

  .save-as-new input {
    flex: 1;
    padding: 0.55rem 0.75rem;
    border-radius: 8px;
    border: 1px solid #333944;
    background: #14161a;
    color: inherit;
  }

  button {
    padding: 0.55rem 1.1rem;
    border-radius: 8px;
    border: none;
    background: #2f81f7;
    color: white;
    font-size: 0.9rem;
    cursor: pointer;
  }

  button:disabled {
    background: #384150;
    color: #6b7280;
    cursor: not-allowed;
  }

  button.secondary {
    background: transparent;
    border: 1px solid #333944;
    color: inherit;
  }

  .error {
    color: #ff6b6b;
    font-size: 0.85rem;
  }

  @media (prefers-color-scheme: light) {
    .raw-text {
      background: #0d1117;
    }
    .save-as-new input {
      background: #f3f4f6;
      color: #1a1a1a;
    }
  }
</style>
