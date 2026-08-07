<script lang="ts">
  import type { CommandSummary } from "../api";
  import { Button } from "$lib/components/ui/button/index.js";
  import PencilIcon from "@lucide/svelte/icons/pencil";
  import Trash2Icon from "@lucide/svelte/icons/trash-2";
  import CheckIcon from "@lucide/svelte/icons/check";

  interface Props {
    command: CommandSummary;
    /** Briefly true right after a successful send, to confirm it visually. */
    fired?: boolean;
    onFire: (command: CommandSummary) => void;
    onEdit: (command: CommandSummary) => void;
    onDelete: (command: CommandSummary) => void;
  }

  let { command, fired = false, onFire, onEdit, onDelete }: Props = $props();
</script>

<li
  class={[
    "bg-card border-border flex items-center gap-1 rounded-xl border p-1.5 shadow-xs",
    "transition-[border-color,box-shadow] duration-500",
    fired && "border-success/60 ring-success/30 ring-2",
  ]}
>
  <button
    type="button"
    class="press hover:bg-foreground/6 focus-visible:border-ring focus-visible:ring-ring/50 flex flex-1 items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-3"
    aria-label="Fire {command.name}"
    onclick={() => onFire(command)}
  >
    <!-- The type badge swaps to a green check on a successful send, in
         place rather than alongside: the row already has an edit and a
         delete button, and a fourth element appearing would shift the
         name. The badge is the same size in both states. -->
    {#if fired}
      <span
        class="bg-success/15 text-success border-success/30 motion-safe:animate-in motion-safe:zoom-in-75 motion-safe:fade-in motion-safe:duration-500 motion-safe:ease-out inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-2 text-xs font-medium"
      >
        <CheckIcon class="size-3" />
        Sent
      </span>
    {:else}
      <!-- Signal type rides on its own token now, not `primary`. Tonal fill so
           the same token works as text in light and dark. -->
      <span
        class={[
          "inline-flex h-5 shrink-0 items-center rounded-full border px-2 text-xs font-medium",
          command.type === "rf"
            ? "bg-rf/12 text-rf border-rf/25"
            : "bg-ir/12 text-ir border-ir/25",
        ].join(" ")}
      >
        {command.type.toUpperCase()}
      </span>
    {/if}
    <span class="font-medium">{command.name}</span>
  </button>
  <Button
    variant="ghost"
    size="icon"
    class="opacity-70 hover:opacity-100"
    aria-label="Edit {command.name}"
    onclick={() => onEdit(command)}
  >
    <PencilIcon />
  </Button>
  <Button
    variant="ghost"
    size="icon"
    class="hover:text-destructive hover:bg-destructive/10 opacity-70 hover:opacity-100"
    aria-label="Delete {command.name}"
    onclick={() => onDelete(command)}
  >
    <Trash2Icon />
  </Button>
</li>
