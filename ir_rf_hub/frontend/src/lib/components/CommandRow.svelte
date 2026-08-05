<script lang="ts">
  import type { CommandSummary } from "../api";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";

  interface Props {
    command: CommandSummary;
    onFire: (command: CommandSummary) => void;
    onEdit: (command: CommandSummary) => void;
    onDelete: (command: CommandSummary) => void;
  }

  let { command, onFire, onEdit, onDelete }: Props = $props();
</script>

<li class="card preset-filled-surface-100-900 flex items-center gap-1 p-1.5">
  <button
    type="button"
    class="hover:preset-tonal-primary flex flex-1 items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors"
    onclick={() => onFire(command)}
  >
    <span
      class={[
        "badge",
        command.type === "rf" ? "preset-tonal-tertiary" : "preset-tonal-primary",
      ].join(" ")}
    >
      {command.type.toUpperCase()}
    </span>
    <span class="font-medium">{command.name}</span>
  </button>
  <button
    type="button"
    class="btn-icon hover:preset-tonal opacity-70 hover:opacity-100"
    aria-label="Edit {command.name}"
    onclick={() => onEdit(command)}
  >
    <PencilIcon class="size-4" />
  </button>
  <button
    type="button"
    class="btn-icon hover:preset-tonal-error opacity-70 hover:opacity-100"
    aria-label="Delete {command.name}"
    onclick={() => onDelete(command)}
  >
    <Trash2Icon class="size-4" />
  </button>
</li>
