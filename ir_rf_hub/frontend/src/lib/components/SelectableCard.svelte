<script lang="ts">
  import { cn } from "$lib/utils.js";
  import type { Snippet } from "svelte";

  interface Props {
    selected: boolean;
    onSelect: () => void;
    disabled?: boolean;
    class?: string;
    children: Snippet;
  }

  let { selected, onSelect, disabled = false, class: className, children }: Props = $props();
</script>

<!-- The one card-picker style, shared by the ESP device pickers and the
     recording wizard's captured-shape picker. Both had grown an identical
     copy of this conditional. -->
<button
  type="button"
  class={cn(
    "press w-full rounded-lg border p-3 text-left transition-colors",
    "focus-visible:border-ring focus-visible:ring-ring/50 outline-none focus-visible:ring-3",
    disabled && "cursor-not-allowed opacity-50",
    selected
      ? "border-primary bg-primary/10"
      : !disabled && "border-border bg-card hover:bg-foreground/6",
    disabled && "border-border bg-card",
    className,
  )}
  aria-pressed={selected}
  {disabled}
  onclick={onSelect}
>
  {@render children()}
</button>
