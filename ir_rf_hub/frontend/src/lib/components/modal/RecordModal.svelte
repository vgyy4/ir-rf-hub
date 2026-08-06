<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import SelectableCard from "../SelectableCard.svelte";
  import TerminalView from "../TerminalView.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import { recordingWizard } from "../../stores/recording.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { commandsStore } from "../../stores/commands.svelte";
  import { devicesWithReceiver } from "../../api";
  import { haptics } from "../../haptics";
  import RadioIcon from "@lucide/svelte/icons/radio";
  import AntennaIcon from "@lucide/svelte/icons/antenna";
  import PencilRulerIcon from "@lucide/svelte/icons/pencil-ruler";
  import ChevronLeftIcon from "@lucide/svelte/icons/chevron-left";
  import ChevronRightIcon from "@lucide/svelte/icons/chevron-right";
  import CheckIcon from "@lucide/svelte/icons/check";
  import PlusIcon from "@lucide/svelte/icons/plus";

  const wizard = recordingWizard;

  let candidateDevices = $derived(
    wizard.type ? devicesWithReceiver(devicesStore.items, wizard.type) : [],
  );

  // Buzz on each newly captured signal. This is the one place haptics earn
  // their keep outright: you are pointing a remote at an ESP, not looking at
  // the screen, and this tells you the capture landed.
  let lastCaptureCount = 0;
  $effect(() => {
    const count = wizard.captures.length;
    if (count > lastCaptureCount) haptics.capture();
    lastCaptureCount = count;
  });

  // The `autofocus` action can't be used here: actions only attach to DOM
  // elements, and Input is a component. shadcn-svelte components expose a
  // bindable `ref` for exactly this.
  let nameInput = $state<HTMLInputElement | null>(null);
  $effect(() => {
    nameInput?.focus();
  });

  async function handleClose() {
    await wizard.close();
  }

  function goBack() {
    haptics.tap();
    void wizard.back();
  }

  async function finish() {
    await wizard.finish();
    if (wizard.error) {
      haptics.error();
    } else {
      haptics.success();
      // The list behind the modal is WebSocket-synced, but the `done` step
      // keeps the modal open over it -- refresh so it's already correct
      // when the user closes rather than a beat later.
      void commandsStore.refresh();
    }
  }
</script>

<Modal open={wizard.step !== "closed"} onClose={handleClose}>
  {#if wizard.step === "choose-type"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">New Recording</h2>
    <p class="text-muted-foreground mb-5 text-sm">What kind of signal are you recording?</p>
    <div class="flex gap-3">
      <button
        type="button"
        class="press border-border bg-card hover:border-ir/40 hover:bg-ir/10 focus-visible:border-ring focus-visible:ring-ring/50 flex flex-1 flex-col items-center gap-2 rounded-lg border p-6 transition-colors outline-none focus-visible:ring-3"
        onclick={() => {
          haptics.tap();
          wizard.chooseType("ir");
        }}
      >
        <RadioIcon class="text-ir size-7" />
        Infrared (IR)
      </button>
      <button
        type="button"
        class="press border-border bg-card hover:border-rf/40 hover:bg-rf/10 focus-visible:border-ring focus-visible:ring-ring/50 flex flex-1 flex-col items-center gap-2 rounded-lg border p-6 transition-colors outline-none focus-visible:ring-3"
        onclick={() => {
          haptics.tap();
          wizard.chooseType("rf");
        }}
      >
        <AntennaIcon class="text-rf size-7" />
        Radio Frequency (RF)
      </button>
    </div>
  {:else if wizard.step === "choose-device"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Choose a receiver</h2>
    <p class="text-muted-foreground mb-5 text-sm">
      Which ESPHome device should listen for the signal? Picking one starts recording straight away.
    </p>
    <DevicePicker
      devices={candidateDevices}
      selectedId={wizard.deviceId}
      onSelect={(id) => {
        haptics.tap();
        void wizard.chooseDevice(id);
      }}
    />

    <!-- Escape hatch for a signal you already have in numeric form, or a
         receiver that isn't reachable right now. -->
    <button
      type="button"
      class="press border-border bg-card hover:bg-muted focus-visible:border-ring focus-visible:ring-ring/50 mt-3 flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors outline-none focus-visible:ring-3"
      onclick={() => {
        haptics.tap();
        wizard.goToRawEntry();
      }}
    >
      <PencilRulerIcon class="text-primary size-5 shrink-0" />
      <span class="flex-1">
        <strong class="block text-sm">Write raw timings instead</strong>
        <span class="text-muted-foreground text-xs">
          Type the signal in by hand -- no device or recording needed.
        </span>
      </span>
      <ChevronRightIcon class="text-muted-foreground size-4 shrink-0" />
    </button>

    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="mt-5 flex justify-between gap-2">
      <Button variant="ghost" onclick={goBack}>
        <ChevronLeftIcon />
        Back
      </Button>
      <Button variant="secondary" onclick={handleClose}>Cancel</Button>
    </div>
  {:else if wizard.step === "raw"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Write raw timings</h2>
    <p class="text-muted-foreground mb-4 text-sm">
      Comma-separated microseconds. Positive = mark (on), negative = space (off) -- the same format
      the ESP records in.
    </p>

    <label class="block">
      <span class="text-muted-foreground text-sm">Signal</span>
      <textarea
        class="focus-visible:ring-ring/50 mt-1 h-28 w-full resize-none rounded-lg bg-neutral-950 p-3 font-mono text-sm text-green-400 outline-none focus-visible:ring-3"
        bind:value={wizard.rawTimingsText}
        placeholder="9000, -4500, 560, -560, 560, -1690"
        spellcheck="false"
      ></textarea>
    </label>

    <label class="mt-3 block">
      <span class="text-muted-foreground text-sm">Repeat signal (optional)</span>
      <textarea
        class="focus-visible:ring-ring/50 mt-1 h-20 w-full resize-none rounded-lg bg-neutral-950 p-3 font-mono text-sm text-green-400 outline-none focus-visible:ring-3"
        bind:value={wizard.repeatTimingsText}
        placeholder="Leave empty for a single-shape command"
        spellcheck="false"
      ></textarea>
      <span class="text-muted-foreground mt-1 block text-xs">
        If set, the signal above fires once and this fires for any repeats beyond the first --
        matching remotes that send a leader once, then a shorter repeat signal while held.
      </span>
    </label>

    <div class="mt-3 flex gap-3">
      <label class="block flex-1">
        <span class="text-muted-foreground text-sm">Repeat count</span>
        <Input type="number" class="mt-1" min="1" bind:value={wizard.repeatCount} />
      </label>
      <label class="block flex-1">
        <span class="text-muted-foreground text-sm">Carrier (Hz)</span>
        <Input type="number" class="mt-1" min="0" bind:value={wizard.carrierFrequencyHz} />
        <span class="text-muted-foreground mt-1 block text-xs">
          {wizard.type === "ir" ? "38000 suits most IR remotes." : "0 -- RF is unmodulated."}
        </span>
      </label>
    </div>

    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="mt-5 flex justify-between gap-2">
      <Button variant="ghost" onclick={goBack}>
        <ChevronLeftIcon />
        Back
      </Button>
      <div class="flex gap-2">
        <Button variant="secondary" onclick={handleClose}>Cancel</Button>
        <Button
          disabled={!wizard.rawTimingsText.trim()}
          onclick={() => {
            haptics.tap();
            wizard.confirmRawEntry();
          }}
        >
          Next
        </Button>
      </div>
    </div>
  {:else if wizard.step === "recording"}
    <h2 class="mb-1 flex items-center gap-2 text-lg font-semibold tracking-tight">
      {#if !wizard.canProceedFromRecording}
        <span class="relative flex size-2.5">
          <span
            class="bg-destructive motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
          ></span>
          <span class="bg-destructive relative inline-flex size-2.5 rounded-full"></span>
        </span>
        Listening&hellip;
      {:else}
        Got it
      {/if}
    </h2>
    <p class="text-muted-foreground mb-5 text-sm">
      {wizard.canProceedFromRecording
        ? "Signal captured. Send another to compare, or carry on."
        : "Point the remote at the receiver and press a button."}
    </p>
    <TerminalView captures={wizard.captures} />
    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="mt-5 flex flex-wrap items-center justify-between gap-2">
      <Button variant="ghost" onclick={goBack} disabled={wizard.busy}>
        <ChevronLeftIcon />
        Back
      </Button>
      <div class="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onclick={() => wizard.clearAndRetry()} disabled={wizard.busy}>
          Clear &amp; retry
        </Button>
        <Button
          variant="secondary"
          onclick={() => wizard.stopRecording()}
          disabled={wizard.busy || wizard.canProceedFromRecording}
        >
          Stop recording
        </Button>
        <Button
          disabled={!wizard.canProceedFromRecording || wizard.busy}
          onclick={() => {
            haptics.tap();
            wizard.proceedFromRecording();
          }}
        >
          Next
        </Button>
      </div>
    </div>
  {:else if wizard.step === "choose-shapes"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Multiple signals captured</h2>
    <p class="text-muted-foreground mb-5 text-sm">
      These didn't look like the same signal repeated, and didn't match a known pattern either --
      choose which one to keep (or two, if your remote sends an initial signal plus a distinct
      repeat signal while held).
    </p>
    <ul class="flex max-h-80 flex-col gap-2 overflow-y-auto">
      {#each wizard.shapeCandidates ?? [] as candidate, i (i)}
        <li>
          <SelectableCard
            selected={wizard.selectedShapeIndices.has(i)}
            onSelect={() => {
              haptics.tap();
              wizard.toggleShapeSelection(i);
            }}
          >
            <div class="flex items-center justify-between gap-3">
              <span class="font-mono text-xs">
                {candidate.timings
                  .slice(0, 6)
                  .map((t) => (t >= 0 ? `+${t}` : `${t}`))
                  .join(" ")}{candidate.timings.length > 6 ? " …" : ""}
              </span>
              <span class="text-muted-foreground shrink-0 text-xs">
                {candidate.edge_count} edges &middot; seen {candidate.occurrences}&times;
              </span>
            </div>
          </SelectableCard>
        </li>
      {/each}
    </ul>
    <p class="text-muted-foreground mt-3 text-xs">
      Pick up to two: the first is used as-is, a second becomes a distinct repeat signal (sent for
      any repeats beyond the first, instead of resending the same one).
    </p>
    {#if wizard.error}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="mt-5 flex justify-between gap-2">
      <Button variant="ghost" onclick={goBack}>
        <ChevronLeftIcon />
        Back
      </Button>
      <Button
        disabled={!wizard.canProceedFromShapes}
        onclick={() => {
          haptics.tap();
          wizard.confirmShapeSelection();
        }}
      >
        Next
      </Button>
    </div>
  {:else if wizard.step === "name"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Name this function</h2>
    <p class="text-muted-foreground mb-3 text-sm">e.g. "TV Power" or "Living Room Fan Speed 2"</p>
    {#if wizard.detectedProtocol}
      <p class="bg-primary/10 text-foreground mb-4 rounded-lg p-2 text-xs">
        Detected a leader signal plus a distinct repeat signal ({wizard.detectedProtocol.name}) --
        both will be saved.
      </p>
    {:else if wizard.repeatTimings}
      <p class="bg-primary/10 text-foreground mb-4 rounded-lg p-2 text-xs">
        Saving two signals: the one you picked first, plus a distinct repeat signal.
      </p>
    {/if}
    <Input
      type="text"
      class="mb-4"
      bind:value={wizard.name}
      bind:ref={nameInput}
      placeholder="Function name"
    />
    <label class="mb-4 block">
      <span class="text-muted-foreground text-sm">Repeat count</span>
      <Input type="number" class="mt-1" min="1" bind:value={wizard.repeatCount} />
      <span class="text-muted-foreground mt-1 block text-xs">
        How many times to send the signal when fired. Pre-filled with how many times your remote
        repeated it during recording -- some receivers need to see the same code several times in a
        row to act on it.
      </span>
    </label>
    {#if wizard.error}
      <Alert.Root variant="destructive" class="mb-3">
        <Alert.Description>{wizard.error}</Alert.Description>
      </Alert.Root>
    {/if}
    <div class="flex justify-between gap-2">
      <Button variant="ghost" onclick={goBack} disabled={wizard.busy}>
        <ChevronLeftIcon />
        Back
      </Button>
      <div class="flex gap-2">
        <Button variant="secondary" onclick={handleClose}>Cancel</Button>
        <Button disabled={!wizard.canFinish || wizard.busy} onclick={finish}>Finish</Button>
      </div>
    </div>
  {:else if wizard.step === "done"}
    <div class="flex flex-col items-center gap-4 py-2 text-center">
      <span
        class="bg-success/15 text-success motion-safe:animate-in motion-safe:zoom-in-50 flex size-14 items-center justify-center rounded-full"
      >
        <CheckIcon class="size-7" />
      </span>
      <div class="space-y-1">
        <h2 class="text-lg font-semibold tracking-tight">Saved "{wizard.savedName}"</h2>
        <p class="text-muted-foreground text-sm">
          {wizard.deviceId
            ? "Capture another off the same remote, or you're done."
            : "Add another command, or you're done."}
        </p>
      </div>
      <div class="flex w-full flex-col gap-2 sm:flex-row-reverse">
        <Button
          class="flex-1"
          onclick={() => {
            haptics.tap();
            void wizard.recordAnother();
          }}
        >
          <PlusIcon />
          Record another
        </Button>
        <Button variant="secondary" class="flex-1" onclick={handleClose}>Done</Button>
      </div>
    </div>
  {/if}
</Modal>
