<script lang="ts">
  import { Dialog, Portal } from "@skeletonlabs/skeleton-svelte";
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

  // Tailwind v4's @starting-style support (via the `starting:` variant) gives
  // a real CSS entrance transition keyed off Zag's data-state attribute --
  // no Svelte transition directives needed, and it composes cleanly with
  // Dialog's own open/close lifecycle instead of racing it.
  const animation =
    "transition-all transition-discrete duration-200 opacity-0 scale-95 " +
    "starting:data-[state=open]:opacity-0 starting:data-[state=open]:scale-95 " +
    "data-[state=open]:opacity-100 data-[state=open]:scale-100";
</script>

<Dialog
  {open}
  onOpenChange={(details) => {
    if (!details.open) onClose();
  }}
  closeOnEscape={closable}
  closeOnInteractOutside={closable}
>
  <Portal>
    <Dialog.Backdrop class="fixed inset-0 z-50 bg-surface-50-950/60 backdrop-blur-md" />
    <Dialog.Positioner class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <Dialog.Content
        class={[
          "card preset-filled-surface-100-900 shadow-2xl overflow-y-auto",
          animation,
          fullscreen
            ? "h-full max-h-none w-full max-w-none rounded-none p-6"
            : "w-full max-w-md p-6",
        ].join(" ")}
      >
        {@render children()}
      </Dialog.Content>
    </Dialog.Positioner>
  </Portal>
</Dialog>
