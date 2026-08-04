<script lang="ts">
  import type { CommandSummary } from "../api";
  import PencilIcon from "@lucide/svelte/icons/pencil";

  interface Props {
    command: CommandSummary;
    onFire: (command: CommandSummary) => void;
    onEdit: (command: CommandSummary) => void;
  }

  let { command, onFire, onEdit }: Props = $props();
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
</li>
