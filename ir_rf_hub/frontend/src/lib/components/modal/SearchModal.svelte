<script lang="ts">
  import Modal from "./Modal.svelte";
  import DevicePicker from "../DevicePicker.svelte";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import * as Alert from "$lib/components/ui/alert/index.js";
  import { searchWizard } from "../../stores/search.svelte";
  import { devicesStore } from "../../stores/devices.svelte";
  import { commandsStore } from "../../stores/commands.svelte";
  import { devicesWithTransmitter } from "../../api";
  import { haptics } from "../../haptics";
  import RadioIcon from "@lucide/svelte/icons/radio";
  import AntennaIcon from "@lucide/svelte/icons/antenna";
  import SearchIcon from "@lucide/svelte/icons/search";
  import RadioTowerIcon from "@lucide/svelte/icons/radio-tower";
  import ChevronLeftIcon from "@lucide/svelte/icons/chevron-left";
  import CheckIcon from "@lucide/svelte/icons/check";
  import PlusIcon from "@lucide/svelte/icons/plus";

  const wizard = searchWizard;

  let queryInput = $state<HTMLInputElement | null>(null);
  $effect(() => {
    if (wizard.step === "search") queryInput?.focus();
  });

  let nameInput = $state<HTMLInputElement | null>(null);
  $effect(() => {
    if (wizard.step === "name") nameInput?.focus();
  });

  const testFireDevices = $derived(
    wizard.type ? devicesWithTransmitter(devicesStore.items, wizard.type) : [],
  );

  async function handleClose() {
    wizard.close();
  }

  function goBack() {
    haptics.tap();
    wizard.back();
  }

  async function finish() {
    await wizard.finish();
    if (wizard.error) {
      haptics.error();
    } else {
      haptics.success();
      void commandsStore.refresh();
    }
  }

  function toggleTestFirePicker() {
    haptics.tap();
    wizard.showTestFirePicker = !wizard.showTestFirePicker;
    wizard.testFireError = null;
  }

  async function handleTestFireDevicePicked(deviceId: string) {
    await wizard.testFire(deviceId);
    if (wizard.testFireError) haptics.error();
    else haptics.success();
  }
</script>

<Modal open={wizard.step !== "closed"} onClose={handleClose}>
  {#if wizard.step === "choose-type"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Search for a command</h2>
    <p class="text-muted-foreground mb-5 text-sm">
      Find a known remote's command by name instead of recording it live. What kind of signal?
    </p>
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
    <div class="mt-5 flex justify-end">
      <Button variant="secondary" onclick={handleClose}>Cancel</Button>
    </div>
  {:else if wizard.step === "search"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Search for a command</h2>
    <p class="text-muted-foreground mb-3 text-sm">
      {wizard.type === "rf"
        ? 'Try a brand and what it does, e.g. "garage door" or "ceiling fan high".'
        : 'Try a brand and what the button does, e.g. "samsung tv power".'}
    </p>
    <div class="relative">
      <SearchIcon class="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
      <Input
        type="text"
        class="pl-9"
        bind:value={wizard.query}
        bind:ref={queryInput}
        oninput={() => wizard.onQueryChange()}
        placeholder={wizard.type === "rf" ? "garage door opener" : "turn on samsung tv"}
      />
    </div>

    {#if wizard.searchError}
      <Alert.Root variant="destructive" class="mt-3">
        <Alert.Description>{wizard.searchError}</Alert.Description>
      </Alert.Root>
    {/if}

    <div class="mt-3 max-h-80 overflow-y-auto">
      {#if wizard.searching}
        <ul class="flex flex-col gap-2" aria-label="Searching">
          {#each [0, 1, 2] as i (i)}
            <li class="bg-card border-border h-14 animate-pulse rounded-lg border"></li>
          {/each}
        </ul>
      {:else if wizard.query.trim().length > 0 && wizard.query.trim().length < 2}
        <p class="text-muted-foreground py-4 text-center text-sm">Keep typing&hellip;</p>
      {:else if wizard.query.trim().length >= 2 && wizard.results.length === 0}
        <p class="text-muted-foreground py-4 text-center text-sm">
          No matches in the bundled database. {wizard.type === "rf"
            ? "RF coverage is much smaller than IR's -- most captured RF codes out there are either raw or use a protocol not covered yet."
            : "Try fewer or different words."} Record it live instead, or write raw timings.
        </p>
      {:else}
          <ul class="flex flex-col gap-2">
            {#each wizard.results as result (result.brand + result.model + result.button)}
              <li>
                <button
                  type="button"
                  class="press border-border bg-card hover:bg-foreground/6 focus-visible:border-ring focus-visible:ring-ring/50 flex w-full items-center justify-between gap-2 rounded-lg border p-3 text-left transition-colors outline-none focus-visible:ring-3"
                  onclick={() => {
                    haptics.tap();
                    wizard.pickResult(result);
                  }}
                >
                  <span class="min-w-0">
                    <strong class="block truncate text-sm font-medium">
                      {result.brand} {result.model}
                    </strong>
                    <span class="text-muted-foreground block truncate text-xs">{result.button}</span>
                  </span>
                  <span
                    class="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-xs"
                  >
                    {result.category}
                  </span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    <div class="mt-5 flex justify-between gap-2">
      <Button variant="ghost" onclick={goBack}>
        <ChevronLeftIcon />
        Back
      </Button>
      <Button variant="secondary" onclick={handleClose}>Cancel</Button>
    </div>
  {:else if wizard.step === "name"}
    <h2 class="mb-1 text-lg font-semibold tracking-tight">Name this function</h2>
    <p class="text-muted-foreground mb-4 text-sm">
      From {wizard.selected?.brand} {wizard.selected?.model} &mdash; {wizard.selected?.button}
    </p>
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
    </label>

    <div class="mb-4">
      <Button variant="outline" size="sm" onclick={toggleTestFirePicker}>
        {#if wizard.testFireSuccess}
          <CheckIcon class="text-success" />
          Sent
        {:else}
          <RadioTowerIcon />
          Test fire
        {/if}
      </Button>
      <span class="text-muted-foreground ml-2 text-xs">Try it before saving.</span>

      {#if wizard.showTestFirePicker}
        <div class="bg-card border-border mt-2 space-y-2 rounded-lg border p-3">
          {#if wizard.testFireError}
            <Alert.Root variant="destructive">
              <Alert.Description>{wizard.testFireError}</Alert.Description>
            </Alert.Root>
          {/if}
          <DevicePicker
            devices={testFireDevices}
            selectedId={null}
            onSelect={handleTestFireDevicePicked}
          />
        </div>
      {/if}
    </div>

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
        class="bg-success/15 text-success motion-safe:animate-in motion-safe:zoom-in-75 motion-safe:fade-in motion-safe:duration-700 motion-safe:ease-out flex size-14 items-center justify-center rounded-full"
      >
        <CheckIcon class="size-7" />
      </span>
      <div class="space-y-1">
        <h2 class="text-lg font-semibold tracking-tight">Saved "{wizard.savedName}"</h2>
        <p class="text-muted-foreground text-sm">Search for another command, or you're done.</p>
      </div>
      <div class="flex w-full flex-col gap-2 sm:flex-row-reverse">
        <Button
          class="flex-1"
          onclick={() => {
            haptics.tap();
            wizard.searchAnother();
          }}
        >
          <PlusIcon />
          Search another
        </Button>
        <Button variant="secondary" class="flex-1" onclick={handleClose}>Done</Button>
      </div>
    </div>
  {/if}
</Modal>
