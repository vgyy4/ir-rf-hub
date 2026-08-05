<script lang="ts">
  import Modal from "./modal/Modal.svelte";
  import { getPairingStatus } from "../api";
  import { copyElementText } from "../clipboard";
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
    setTimeout(() => (copied = false), 2000);
  }

  $effect(() => {
    pollTimer = setInterval(async () => {
      const status = await getPairingStatus().catch(() => null);
      if (status?.paired) {
        clearInterval(pollTimer);
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
    <div class="bg-primary-500/15 text-primary-500 rounded-full p-4">
      <LinkIcon class="size-8" />
    </div>

    <div class="space-y-1.5">
      <h2 class="h3">Connect the companion integration</h2>
      <p class="text-surface-600-400 text-sm">
        Install the <strong>IR/RF Command Hub</strong> integration in Home Assistant. It should find this
        App on its own -- check Settings &rarr; Devices &amp; services for a "Discovered" card and confirm
        it. This screen will move on automatically once you're paired.
      </p>
    </div>

    <div class="w-full space-y-2">
      <p class="text-surface-500 text-xs">Didn't get a "Discovered" card? Paste this code into the
        integration's setup form manually:</p>
      <div
        class="border-surface-300-700 bg-surface-50-950 w-full overflow-x-auto rounded-lg border p-4 text-left"
      >
        <code bind:this={codeEl} class="font-mono text-xs break-all">{code}</code>
      </div>
      <button type="button" class="btn preset-filled-primary-500 w-full" onclick={copyCode}>
        {#if copied}
          <CheckIcon class="size-4" />
          Copied
        {:else}
          <CopyIcon class="size-4" />
          Copy pairing code
        {/if}
      </button>
    </div>

    <div class="text-surface-500 flex items-center gap-2 text-xs">
      <span class="bg-primary-500 relative flex size-2">
        <span class="bg-primary-500 absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
        ></span>
        <span class="bg-primary-500 relative inline-flex size-2 rounded-full"></span>
      </span>
      Waiting for pairing&hellip;
    </div>
  </div>
</Modal>
