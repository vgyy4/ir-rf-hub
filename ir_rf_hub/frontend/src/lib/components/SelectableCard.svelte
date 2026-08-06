<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";

  interface Props {
    selected: boolean;
    onSelect: () => void;
    class?: string;
    children: Snippet;
  }

  let { selected, onSelect, class: className, children }: Props = $props();
</script>

<!-- The one card-picker style, shared by the ESP device pickers and the
     recording wizard's captured-shape picker. Both had grown an identical
     copy of this conditional. -->
<button
  type="button"
  class={cn(
    "press w-full rounded-lg border p-3 text-left transition-colors",
    "focus-visible:border-ring focus-visible:ring-ring/50 outline-none focus-visible:ring-3",
    selected
      ? "border-primary bg-primary/10"
      : "border-border bg-card hover:bg-muted",
    className,
  )}
  aria-pressed={selected}
  onclick={onSelect}
>
  {@render children()}
</button>
