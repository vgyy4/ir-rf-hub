<script lang="ts">
  interface Props {
    captures: number[][];
  }

  let { captures }: Props = $props();

  let container: HTMLDivElement | undefined = $state();

  $effect(() => {
    // re-run whenever captures changes; scroll to the newest entry
    void captures.length;
    if (container) container.scrollTop = container.scrollHeight;
  });

  function formatCapture(timings: number[]): string {
    // mark/space pairs, positive = mark (on), negative = space (off) --
    // exactly the raw format ir_rf_proxy delivers, no reinterpretation.
    return timings.map((t) => (t >= 0 ? `+${t}` : `${t}`)).join("  ");
  }
</script>

<!-- Deliberately stays dark regardless of theme -- a raw-signal console
     reads as a console, the same way an IDE's terminal panel does. -->
<div
  bind:this={container}
  role="log"
  aria-live="polite"
  class="h-45 overflow-y-auto rounded-lg bg-neutral-950 p-3 font-mono text-xs whitespace-pre text-green-400"
>
  {#if captures.length === 0}
    <p class="m-0 text-neutral-500 italic">waiting for signal&hellip;</p>
  {/if}
  {#each captures as capture, i (i)}
    <div class="flex gap-2 leading-relaxed">
      <span class="shrink-0 text-sky-400">#{i + 1}</span>
      <span class="flex-1 overflow-x-auto">{formatCapture(capture)}</span>
      <span class="shrink-0 text-neutral-500">({capture.length} edges)</span>
    </div>
  {/each}
</div>
