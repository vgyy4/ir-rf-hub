<script lang="ts">
  import Modal from "./modal/Modal.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { getPairingStatus } from "../api";
  import { copyElementText } from "../clipboard";
  import { haptics } from "../haptics";
  import CopyIcon from "@lucide/svelte/icons/copy";
  import CheckIcon from "@lucide/svelte/icons/check";
  import LinkIcon from "@lucide/svelte/icons/link-2";

  interface Props {
    code: string;
    onPaired: () => void;
  }

  let { code, onPaired }: Props = $props();

  let copied = $state(false);
  let codeEl: HTMLElement | undefined = $state();
  let pollTimer: ReturnType<typeof setInterval> | undefined;

  async function copyCode() {
    if (!codeEl || !(await copyElementText(codeEl, code))) return;
    copied = true;
    haptics.success();
    setTimeout(() => (copied = false), 2000);
  }

  $effect(() => {
    pollTimer = setInterval(async () => {
      const status = await getPairingStatus().catch(() => null);
      if (status?.paired) {
        clearInterval(pollTimer);
        haptics.success();
        onPaired();
      }
    }, 2500);
    return () => clearInterval(pollTimer);
  });
</script>

<!-- No close handler at all: this gate genuinely cannot be dismissed except
     by successfully pairing, matching the requirement that the rest of the
     app stays unreachable until then. -->
<Modal open={true} onClose={() => {}} closable={false}>
  <div class="flex flex-col items-center gap-5 text-center">
    <div class="bg-primary/15 text-primary rounded-full p-4">
      <LinkIcon class="size-8" />
    </div>

    <div class="space-y-1.5">
      <h2 class="text-xl font-semibold tracking-tight">Connect the companion integration</h2>
      <p class="text-muted-foreground text-sm">
        Install the <strong>IR/RF Hub</strong> integration in Home Assistant. It should find
        this App on its own -- check Settings &rarr; Devices &amp; services for a "Discovered" card
        and confirm it. This screen will move on automatically once you're paired.
      </p>
    </div>

    <div class="w-full space-y-2">
      <p class="text-muted-foreground text-xs">
        Didn't get a "Discovered" card? Paste this code into the integration's setup form manually:
      </p>
      <div class="border-border bg-muted w-full overflow-x-auto rounded-lg border p-4 text-left">
        <code bind:this={codeEl} class="font-mono text-xs break-all">{code}</code>
      </div>
      <Button class="w-full" onclick={copyCode}>
        {#if copied}
          <CheckIcon class="motion-safe:animate-in motion-safe:zoom-in-75 motion-safe:fade-in motion-safe:duration-500 motion-safe:ease-out" />
          Copied
        {:else}
          <CopyIcon />
          Copy pairing code
        {/if}
      </Button>
    </div>

    <div class="text-muted-foreground flex items-center gap-2 text-xs">
      <span class="relative flex size-2">
        <span
          class="bg-primary motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
        ></span>
        <span class="bg-primary relative inline-flex size-2 rounded-full"></span>
      </span>
      Listening for the handshake&hellip;
    </div>
  </div>
</Modal>
