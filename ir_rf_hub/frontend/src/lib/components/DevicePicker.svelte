<script lang="ts">
  import type { EspDeviceSummary } from "../api";
  import SelectableCard from "./SelectableCard.svelte";
  import CheckIcon from "@lucide/svelte/icons/check";

  interface Props {
    devices: EspDeviceSummary[];
    selectedId: string | null;
    onSelect: (deviceId: string) => void;
  }

  let { devices, selectedId, onSelect }: Props = $props();

  const ONLINE_STATES = new Set(["idle", "rx_active", "tx_active", "rx_settling", "tx_settling"]);
</script>

{#if devices.length === 0}
  <p class="text-muted-foreground text-sm italic">
    No matching ESPHome devices found. Add one with the "Devices" button first -- it'll need
    <code>ir_rf_proxy</code> in its ESPHome YAML (see the
    <a
      class="text-foreground underline underline-offset-2"
      href="https://github.com/vgyy4/ir-rf-hub/blob/main/ir_rf_hub/DOCS.md"
      target="_blank"
      rel="noopener noreferrer"
    >
      Documentation tab or DOCS.md
    </a>
    for a copy-paste example).
  </p>
{:else}
  <ul class="flex max-h-70 flex-col gap-2 overflow-y-auto">
    {#each devices as device (device.id)}
      {@const online = ONLINE_STATES.has(device.connection_state)}
      <li>
        <SelectableCard
          selected={device.id === selectedId}
          disabled={!online}
          onSelect={() => online && onSelect(device.id)}
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-medium">{device.name}</span>
            <div class="flex items-center gap-2">
              <span
                class={[
                  "text-xs tracking-wide uppercase",
                  online ? "text-success" : "text-muted-foreground",
                ].join(" ")}
              >
                {device.connection_state}
              </span>
              {#if device.id === selectedId}
                <CheckIcon class="text-primary size-4" />
              {/if}
            </div>
          </div>
          {#if !online}
            <p class="text-muted-foreground mt-0.5 text-xs">Not reachable right now</p>
          {/if}
        </SelectableCard>
      </li>
    {/each}
  </ul>
{/if}
