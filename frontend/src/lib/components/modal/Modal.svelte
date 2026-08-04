<script lang="ts">
  import { fade, scale } from "svelte/transition";
  import { quintOut } from "svelte/easing";
  import type { Snippet } from "svelte";

  interface Props {
    open: boolean;
    onClose: () => void;
    fullscreen?: boolean;
    children: Snippet;
  }

  let { open, onClose, fullscreen = false, children }: Props = $props();

  function onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) onClose();
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") onClose();
  }
</script>

<svelte:window onkeydown={open ? onKeydown : undefined} />

{#if open}
  <div
    class="backdrop"
    role="presentation"
    transition:fade={{ duration: 180 }}
    onclick={onBackdropClick}
  >
    <div
      class="panel"
      class:fullscreen
      transition:scale={{ start: 0.94, duration: 220, easing: quintOut }}
    >
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(10, 12, 16, 0.55);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
  }

  .panel {
    background: #1c1f26;
    color: #e6e6e6;
    border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    width: min(480px, calc(100vw - 2rem));
    max-height: calc(100vh - 4rem);
    overflow-y: auto;
    padding: 1.75rem;
  }

  .panel.fullscreen {
    width: calc(100vw - 2rem);
    height: calc(100vh - 2rem);
    max-height: none;
    border-radius: 12px;
  }

  @media (prefers-color-scheme: light) {
    .panel {
      background: #ffffff;
      color: #1a1a1a;
    }
  }
</style>
