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

<div class="terminal" bind:this={container} role="log" aria-live="polite">
  {#if captures.length === 0}
    <p class="waiting">waiting for signal&hellip;</p>
  {/if}
  {#each captures as capture, i (i)}
    <div class="line">
      <span class="index">#{i + 1}</span>
      <span class="samples">{formatCapture(capture)}</span>
      <span class="count">({capture.length} edges)</span>
    </div>
  {/each}
</div>

<style>
  .terminal {
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    font-size: 0.8rem;
    background: #0c0e12;
    color: #7ee787;
    border-radius: 8px;
    padding: 0.75rem;
    height: 180px;
    overflow-y: auto;
    white-space: pre;
  }

  .waiting {
    color: #6b7280;
    font-style: italic;
    margin: 0;
  }

  .line {
    display: flex;
    gap: 0.5rem;
    line-height: 1.5;
  }

  .index {
    color: #58a6ff;
    flex-shrink: 0;
  }

  .samples {
    overflow-x: auto;
    flex: 1;
  }

  .count {
    color: #6b7280;
    flex-shrink: 0;
  }

  @media (prefers-color-scheme: light) {
    .terminal {
      background: #0d1117;
    }
  }
</style>
