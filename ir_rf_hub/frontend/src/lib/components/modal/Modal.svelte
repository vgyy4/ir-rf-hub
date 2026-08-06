<script lang="ts">
  import * as Dialog from "$lib/components/ui/dialog/index.js";
  import type { Snippet } from "svelte";

  interface Props {
    open: boolean;
    onClose: () => void;
    /** Non-dismissable: no Escape, no backdrop click. Used by the pairing gate. */
    closable?: boolean;
    fullscreen?: boolean;
    children: Snippet;
  }

  let { open, onClose, closable = true, fullscreen = false, children }: Props = $props();
</script>

<Dialog.Root
  {open}
  onOpenChange={(next) => {
    if (!next) onClose();
  }}
>
  <Dialog.Content
    showCloseButton={closable}
    escapeKeydownBehavior={closable ? "close" : "ignore"}
    interactOutsideBehavior={closable ? "close" : "ignore"}
    class={fullscreen
      ? "h-dvh max-h-none w-screen max-w-none overflow-y-auto rounded-none p-6 sm:max-w-none"
      : "max-h-[calc(100dvh-4rem)] overflow-y-auto p-5 sm:max-w-md"}
  >
    {@render children()}
  </Dialog.Content>
</Dialog.Root>
